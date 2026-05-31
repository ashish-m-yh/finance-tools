import json
import re
import sys
import os
from collections import OrderedDict
from enum import Enum

sms_parser_logger = None

if 'SMS_APP_MODE' not in os.environ:
    os.environ['SMS_APP_MODE'] = 'prod'

if 'SMS_APP_MODE' in os.environ and os.environ['SMS_APP_MODE'] == 'prod':
    from flask_init import labs_app
    from common import ExceptionLogger

    sms_parser_logger = labs_app.logger


class AccountType(Enum):
    LOAN = 'loan'
    BANK = 'bank'
    CARD = 'card'
    DEBIT_CARD = 'debit_card'


class SmsAttributes(Enum):
    ACCOUNT_TYPE = 'account_type'
    ACCOUNT_NO = 'account'
    TXN_AMOUNT = 'amount'
    BALANCE = 'balance'
    BANK_NAME = 'bank_name'
    CLASS = 'class'
    MATCHED_RULES = 'matched_rules'
    ATTR = 'attr'
    LOAN_TYPE = 'loan_type'
    PAYMENT_TYPE = 'payment_type'


class RuleAttributes(Enum):
    NEG_PATTERN = 'neg_pattern'
    PATTERN = 'pattern'
    POSITION = 'position'


class TxnClasses(Enum):
    CREDIT = 'credit'
    DEBIT = 'debit'


class RedFlags(Enum):
    NO_FUNDS = 'info-red-nofunds'
    NO_PAYMENT = 'info-red-payment'
    LOAN_DEFAULT = 'info-red-loanDefault'


class Overrides(Enum):
    REGEX = 0
    NEW_CLASS = 1
    OLD_CLASS = 2
    ALL_CLASSES = 'all'


class RuleEngine(object):
    """
    Part of SMS parsing and logic for rule engine extraction from a file.

    RuleEngine Class contains all the function for parsing out sms and Classifying it into multiple transaction
    classes and extracting the transaction related information like amount, account , balance etc.

    Typical Usage
        >>> from rule_engine import RuleEngine
        >>> rule_engine_obj = RuleEngine(rules_file='/user/abc/Documents/rules.txt', bank_file='/user/abc/bank.json', acct_types_file='/usr/abc/acct_types.json')
        >>> rule_engine_obj.run(sms='Sms Text', sender='VM-AIRBNK')

    Attributes:-
        - rules_file:- Destination to the rules_file in the format of a json object
            `` { "class": "debit",
            "pattern": "(inr|rs\\.?)\\s*([0-9\\.\\,]+).*?credited\\s+to\\s+your\\s+(.*?)card", \
            "position": { "amount": 2 },
            \"neg_pattern": "using\\s+card|credited\\s+to\\s+your\\s+a\\/c|credited\\s+to\\s+your\\s+account" } ``

        - bank_file:- Destination to the bank ,mapping with it's abbrev.
        - acct_types_file:- File to map patterns to different account types.
    """
    def __init__(self, rules_file, bank_file=None, acct_types_file=None, override_file=None):
        self._rules = self._read_meta(rules_file)

        if bank_file:
            self.bank_mapping = self._parse_mapping_file(bank_file)

        if acct_types_file:
            self.acct_types_mapping = self._parse_mapping_file(acct_types_file)

        if override_file:
            self.overrides = self._parse_mapping_file(override_file)

    # read rules JSON file
    def _read_meta(self, filename):
        lines = []

        try:
            fh = open(filename, 'r')
            lines = fh.readlines()
            fh.close()

            lines = [line for line in lines if line.strip() != '']
        except Exception as e:
            raise Exception('Rules files could not be opened ' + str(e))

        return lines

    # read JSON configuration files
    def _parse_mapping_file(self, filename):
        with open(filename, 'r') as fh:
            data = json.load(fh, object_pairs_hook=OrderedDict)
        return data

    # this is the entry point from where all internal methods are called
    def run(self, sms, sender=None):
        info = None
        sms = self._normalize_text(sms)

        info = self._match_rules(self._rules, sms)
        info = self._result_post_process(info, sms)

        if sender:
            try:
                bank_name = self._extract_bank_name(sender, self.bank_mapping)
                if isinstance(info, dict):
                    info[SmsAttributes.BANK_NAME.value] = bank_name
            except:
                ExceptionLogger.print_and_log_exception(sms_parser_logger)
                pass

        return info

    # clean account no. and set account type here
    def _clean_account_no(self, account_no, sms):
        sms = sms.replace('no.', 'no')
        normalized_acct_no = account_no.replace('no.', '').replace('no', '').strip()
        normalized_acct_no = re.sub(r'yes$|is$|has$|thru$|auth.*?$', '', normalized_acct_no.lower())

        acct_type = None

        # try to identify if it is loan, card or bank a/c based on defined prefixes
        for acct_type_pat in self.acct_types_mapping:
            acct_type_pat = acct_type_pat.rstrip()

            acct_pattern1 = '.*?' + acct_type_pat + '\\s*' + re.escape(account_no) + '.*?'
            acct_pattern2 = '.*?' + acct_type_pat + '\\s*' + re.escape(normalized_acct_no) + '.*?'

            if re.match(acct_pattern1, sms, re.IGNORECASE | re.MULTILINE) or re.match(acct_pattern2, sms, re.IGNORECASE | re.MULTILINE):
                if self.acct_types_mapping is not None and self.acct_types_mapping != '':
                    acct_type = self.acct_types_mapping[acct_type_pat]

                    if (acct_type == AccountType.CARD.value):
                        debit_cd_pattern1 = '.*? debit\\s*' + acct_type_pat + '\\s*' + re.escape(account_no) + '.*?'
                        debit_cd_pattern2 = '.*? debit\\s*' + acct_type_pat + '\\s*' + re.escape(normalized_acct_no) + '.*?'

                        if (re.match(debit_cd_pattern1, sms, re.IGNORECASE | re.MULTILINE) \
                            or re.match(debit_cd_pattern2, sms, re.IGNORECASE | re.MULTILINE)):
                                acct_type = AccountType.DEBIT_CARD.value
                        else:
                            if re.search('by\\s+debit\\s+card\\s+swipe', sms, re.IGNORECASE | re.MULTILINE):
                                acct_type = AccountType.DEBIT_CARD.value


        normalized_acct_no = re.sub(r'\s+.*', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'^[a-z]+$', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'^\*+', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'^x+', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'^n+', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'[:;,\s].*', '', normalized_acct_no)

        for char in [' ', ',', ':', ';', '.']:
            matched = normalized_acct_no.split(char)
            normalized_acct_no = matched[0]

        normalized_acct_no = re.sub(r'\)|\-', '', normalized_acct_no)
        normalized_acct_no = re.sub(r'^x+', '', normalized_acct_no)

        if re.search('[0-9]', normalized_acct_no) and not re.search('@', normalized_acct_no):
            normalized_acct_no = re.sub(r'^0+', '', normalized_acct_no)

        normalized_acct_no = re.sub(r'^[a-zA-Z]+$', '', normalized_acct_no)

        return (normalized_acct_no, acct_type)

    def _result_post_process(self, info, sms):
        for number_field in [SmsAttributes.TXN_AMOUNT.value, SmsAttributes.BALANCE.value]:
            if number_field in info:
                info[number_field] = info[number_field].replace(',', '')
                numbers = re.findall(r'\d+', info[number_field])
                if len(numbers) > 0:
                    info[number_field] = numbers[0]

                if not info[number_field].isdigit():
                    del info[number_field]

        txn_type = None

        # credit to CC or loan account is actually a debit txn
        if SmsAttributes.ACCOUNT_TYPE.value in info and info[SmsAttributes.ACCOUNT_TYPE.value] is not None and \
            info[SmsAttributes.ACCOUNT_TYPE.value].strip() != '':
            if (info[SmsAttributes.ACCOUNT_TYPE.value] == AccountType.LOAN.value or \
            info[SmsAttributes.ACCOUNT_TYPE.value] == AccountType.CARD.value):

                if SmsAttributes.CLASS.value in info and TxnClasses.CREDIT.value in info[SmsAttributes.CLASS.value]:
                    info[SmsAttributes.CLASS.value].remove(TxnClasses.CREDIT.value)

                    if TxnClasses.DEBIT.value not in info[SmsAttributes.CLASS.value]:
                        info[SmsAttributes.CLASS.value].append(TxnClasses.DEBIT.value)

                txn_type = info[SmsAttributes.ACCOUNT_TYPE.value]
        else:
            # acccount type does not exist, so it could be a loan account which was not detected or bank account
            # if classes are only loan classes, then definite loan account else bank account
            loan_classes = list(filter(lambda x: re.search('loan', x), info[SmsAttributes.CLASS.value]))

            if len(loan_classes) > 0:
                info[SmsAttributes.ACCOUNT_TYPE.value] = AccountType.LOAN.value

        # In case of red flag due to non-payment, set if it is loan payment miss or any other
        if SmsAttributes.CLASS.value in info and (RedFlags.NO_FUNDS.value in info[SmsAttributes.CLASS.value] or \
            RedFlags.NO_PAYMENT.value in info[SmsAttributes.CLASS.value]):

            if not txn_type == AccountType.LOAN.value:
                txn_type = 'other'

            if SmsAttributes.ATTR.value in info:
                if SmsAttributes.LOAN_TYPE.value in info[SmsAttributes.ATTR.value]:
                    txn_type = AccountType.LOAN.value

                info[SmsAttributes.ATTR.value][SmsAttributes.PAYMENT_TYPE.value] = txn_type
            else:
                info[SmsAttributes.ATTR.value] = {SmsAttributes.PAYMENT_TYPE.value: txn_type}

            for rule_key in [TxnClasses.CREDIT.value, TxnClasses.DEBIT.value]:
                if rule_key in info[SmsAttributes.CLASS.value]:
                    info[SmsAttributes.CLASS.value].remove(rule_key)

        # If loan default, then set added category of non-payment red flag
        if SmsAttributes.CLASS.value in info and RedFlags.LOAN_DEFAULT.value in info[SmsAttributes.CLASS.value] \
            and RedFlags.NO_PAYMENT.value not in info[SmsAttributes.CLASS.value]:
            info[SmsAttributes.CLASS.value].append(RedFlags.NO_PAYMENT.value)

        # there are some generic overrides so we don't have to set negative pattern for multiple rules
        # eg. credit to beneficiary account is also a debit, certain kind of messages are not classified based on keywords/patterns
        if self.overrides is not None:
            for override_rule in self.overrides['override']:
                if re.search(override_rule[Overrides.REGEX.value], sms, re.IGNORECASE | re.MULTILINE):
                    if (override_rule[Overrides.OLD_CLASS.value] == Overrides.ALL_CLASSES.value) and \
                        SmsAttributes.TXN_AMOUNT.value in info and int(info[SmsAttributes.TXN_AMOUNT.value]) > 0:
                        if override_rule[Overrides.NEW_CLASS.value] != '':
                            info[SmsAttributes.CLASS.value] = override_rule[Overrides.NEW_CLASS.value]
                        else:
                            try:
                                del info[SmsAttributes.CLASS.value]
                                del info[SmsAttributes.TXN_AMOUNT.value]
                            except:
                                pass

        return info

    # first step is to sanitize the message so that parsing is easier but without information loss
    def _normalize_text(self, sms):
        sms = sms.strip().replace("'", "").replace('"', '').replace('rs.', 'rs. ')\
            .replace('inr.', 'inr ').replace('inr', 'inr ').replace('through', ' through')\
            .replace('debited', ' debited').replace('credited', ' credited').replace('  ', ' ')
        return sms

    # mutliple patterns may match to extract account no.
    # but all matching rules may not give it in the correct form
    # so we push them all into a set and return the most probabilistic one based on a simple rule (which is almost always right)
    def _find_most_likely_acct_no(self, accounts_set, sms):
        def _check(elt):
            return len(elt.replace("\s+", "\s").split(' '))

        likely_accts = sorted(accounts_set, key=_check)
        prob_acct = None

        for likely_acct in likely_accts:
            prob_acct = self._clean_account_no(likely_acct, sms)
            if prob_acct is not None and prob_acct[0].strip() != '':
                break

        return prob_acct

    # match each rules which is a regex match associated with certain attributes and classes
    # regex should be not too greedy but not too restricting either
    # it may parse out multiple attributes as defined in the JSON config
    def _match_rules(self, rule_list, sms):
        info = {SmsAttributes.MATCHED_RULES.value: set(), SmsAttributes.CLASS.value: set()}

        i = 0
        accounts_set = set()

        for rule_str in rule_list:
            i = i + 1

            if not rule_str.startswith('#'):
                rule = None
                match = None

                try:
                    rule = json.loads(rule_str)
                    match = re.search(rule[RuleAttributes.PATTERN.value], sms, re.IGNORECASE | re.MULTILINE)
                except Exception as e:
                    sys.stderr.write('Could not parse rule on line ' + str(i) + " " + rule_str + "\n")

                if match is not None:
                    if RuleAttributes.NEG_PATTERN.value in rule:
                        if re.search(rule[RuleAttributes.NEG_PATTERN.value], sms, re.IGNORECASE | re.MULTILINE):
                            continue

                    if SmsAttributes.ATTR.value in rule:
                        info[SmsAttributes.ATTR.value] = rule[SmsAttributes.ATTR.value]

                    info[SmsAttributes.CLASS.value].add(rule[SmsAttributes.CLASS.value])
                    info[SmsAttributes.MATCHED_RULES.value].add(rule_str + ' ' + str(i))

                    parts = match.groups()

                    if RuleAttributes.POSITION.value in rule:
                        for field in rule[RuleAttributes.POSITION.value].keys():
                            try:
                                info[field] = parts[rule[RuleAttributes.POSITION.value][field]-1]
                            except Exception as e:
                                sys.stderr.write(e)

                    if SmsAttributes.ACCOUNT_NO.value in info and info[SmsAttributes.ACCOUNT_NO.value].strip() != '':
                        info[SmsAttributes.ACCOUNT_NO.value] = info[SmsAttributes.ACCOUNT_NO.value].replace(',', '')
                        accounts_set.add(info[SmsAttributes.ACCOUNT_NO.value].strip())

        account_no_exists = True

        if accounts_set is not None and len(accounts_set) > 0:
            (prob_acct_no, prob_acct_type) = self._find_most_likely_acct_no(accounts_set, sms)

            if prob_acct_type is None:
                prob_acct_type = ''

            if prob_acct_no is not None and prob_acct_no.strip() != '':
                info[SmsAttributes.ACCOUNT_NO.value] = prob_acct_no
                info[SmsAttributes.ACCOUNT_TYPE.value] = prob_acct_type
            else:
                account_no_exists = False
        else:
            account_no_exists = False

        if not account_no_exists:
            try:
                del info[SmsAttributes.ACCOUNT_NO.value]
                del info[SmsAttributes.ACCOUNT_TYPE.value]
            except:
                pass

        info[SmsAttributes.MATCHED_RULES.value] = list(info[SmsAttributes.MATCHED_RULES.value])
        info[SmsAttributes.CLASS.value] = list(info[SmsAttributes.CLASS.value])

        return info

    def _extract_bank_name(self, sender, bank_mapping):
        if isinstance(bank_mapping, list):
            for item in bank_mapping:
                if str(item['string']).lower() in str(sender).lower():
                    if item['Class'] == 'BankName':
                        return item['Name']
                    else:
                        return sender[-6:]
            return sender[-6:]
