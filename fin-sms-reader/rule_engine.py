import json
import re
import sys
import os
from collections import OrderedDict
from enum import Enum


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
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class RedFlags(Enum):
    EMPTY_VALUE = 'info-flag-empty'
    MISSING_PROCESS = 'info-flag-missing'
    CRITICAL_DEFAULT = 'info-flag-default'


class Overrides(Enum):
    REGEX = 0
    NEW_CLASS = 1
    OLD_CLASS = 2
    ALL_CLASSES = 'all'


class RuleEngine(object):
    """
    Generalized pattern-matching engine for text analysis and data classification.

    RuleEngine Class contains all the function for parsing out raw text entries and Classifying it into multiple 
    transaction/entity classes and extracting relation information like metric, index, balance etc.

    Typical Usage
        >>> from rule_engine import RuleEngine
        >>> rule_engine_obj = RuleEngine(rules_file='/user/abc/Documents/rules.txt', bank_file='/user/abc/bank.json', acct_types_file='/usr/abc/acct_types.json')
        >>> rule_engine_obj.run(sms='Raw Text Content', sender='SOURCE_ID_01')
    """
    def __init__(self, rules_file, bank_file=None, acct_types_file=None, override_file=None):
        self._rules = self._read_meta_config(rules_file)

        if bank_file:
            self.bank_mapping = self._load_json_mapping(bank_file)

        if acct_types_file:
            self.acct_types_mapping = self._load_json_mapping(acct_types_file)

        if override_file:
            self.overrides = self._load_json_mapping(override_file)

    def _read_meta_config(self, filename):
        lines = []

        try:
            fh = open(filename, 'r')
            lines = fh.readlines()
            fh.close()

            lines = [line for line in lines if line.strip() != '']
        except Exception as e:
            raise Exception('Rules files could not be opened ' + str(e))

        return lines

    def _load_json_mapping(self, filename):
        with open(filename, 'r') as fh:
            data = json.load(fh, object_pairs_hook=OrderedDict)
        return data

    def run(self, sms, sender=None):
        info = None
        sms = self._clean_raw_text(sms)

        info = self._execute_pattern_matching(self._rules, sms)
        info = self._apply_post_processing_rules(info, sms)

        if sender:
            try:
                bank_name = self._resolve_source_identity(sender, self.bank_mapping)
                if isinstance(info, dict):
                    info[SmsAttributes.BANK_NAME.value] = bank_name
            except:
                pass

        return info

    def _parse_and_validate_identifier(self, account_no, sms):
        sms = sms.replace('no.', 'no')
        normalized_acct_no = account_no.replace('no.', '').replace('no', '').strip()
        normalized_acct_no = re.sub(r'yes$|is$|has$|thru$|auth.*?$', '', normalized_acct_no.lower())

        acct_type = None

        for acct_type_pat in self.acct_types_mapping:
            acct_type_pat = acct_type_pat.rstrip()

            acct_pattern1 = '.*?' + acct_type_pat + '\\s*' + re.escape(account_no) + '.*?'
            acct_pattern2 = '.*?' + acct_type_pat + '\\s*' + re.escape(normalized_acct_no) + '.*?'

            if re.match(acct_pattern1, sms, re.IGNORECASE | re.MULTILINE) or re.match(acct_pattern2, sms, re.IGNORECASE | re.MULTILINE):
                if self.acct_types_mapping is not None and self.acct_types_mapping != '':
                    acct_type = self.acct_types_mapping[acct_type_pat]

                    if (acct_type == AccountType.BANK.value):
                        debit_cd_pattern1 = '.*? virtual\\s*' + acct_type_pat + '\\s*' + re.escape(account_no) + '.*?'
                        debit_cd_pattern2 = '.*? virtual\\s*' + acct_type_pat + '\\s*' + re.escape(normalized_acct_no) + '.*?'

                        if (re.match(debit_cd_pattern1, sms, re.IGNORECASE | re.MULTILINE) \
                            or re.match(debit_cd_pattern2, sms, re.IGNORECASE | re.MULTILINE)):
                                acct_type = AccountType.DEBIT_CARD.value
                        else:
                            if re.search('by\\s+virtual\\s+access\\s+token', sms, re.IGNORECASE | re.MULTILINE):
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

    def _apply_post_processing_rules(self, info, sms):
        for number_field in [SmsAttributes.TXN_AMOUNT.value, SmsAttributes.BALANCE.value]:
            if number_field in info:
                info[number_field] = info[number_field].replace(',', '')
                numbers = re.findall(r'\d+', info[number_field])
                if len(numbers) > 0:
                    info[number_field] = numbers[0]

                if not info[number_field].isdigit():
                    del info[number_field]

        txn_type = None

        # Check if account_type exists, is not None, and isn't purely empty whitespace
        if SmsAttributes.ACCOUNT_TYPE.value in info and info[SmsAttributes.ACCOUNT_TYPE.value] is not None and \
            info[SmsAttributes.ACCOUNT_TYPE.value].strip() != '':
            if (info[SmsAttributes.ACCOUNT_TYPE.value] == AccountType.LOAN.value or \
            info[SmsAttributes.ACCOUNT_TYPE.value] == AccountType.BANK.value):

                if SmsAttributes.CLASS.value in info and TxnClasses.INBOUND.value in info[SmsAttributes.CLASS.value]:
                    info[SmsAttributes.CLASS.value].remove(TxnClasses.INBOUND.value)

                    if TxnClasses.OUTBOUND.value not in info[SmsAttributes.CLASS.value]:
                        info[SmsAttributes.CLASS.value].append(TxnClasses.OUTBOUND.value)

                txn_type = info[SmsAttributes.ACCOUNT_TYPE.value]
        else:
            loan_classes = list(filter(lambda x: re.search('loan', x), info[SmsAttributes.CLASS.value]))

            if len(loan_classes) > 0:
                info[SmsAttributes.ACCOUNT_TYPE.value] = AccountType.LOAN.value
            else:
                # Fallback addition: If empty/not found and not categorized as a loan, default to bank
                info[SmsAttributes.ACCOUNT_TYPE.value] = AccountType.BANK.value

        if SmsAttributes.CLASS.value in info and (RedFlags.EMPTY_VALUE.value in info[SmsAttributes.CLASS.value] or \
            RedFlags.MISSING_PROCESS.value in info[SmsAttributes.CLASS.value]):

            if not txn_type == AccountType.LOAN.value:
                txn_type = 'alternative'

            if SmsAttributes.ATTR.value in info:
                if SmsAttributes.LOAN_TYPE.value in info[SmsAttributes.ATTR.value]:
                    txn_type = AccountType.LOAN.value

                info[SmsAttributes.ATTR.value][SmsAttributes.PAYMENT_TYPE.value] = txn_type
            else:
                info[SmsAttributes.ATTR.value] = {SmsAttributes.PAYMENT_TYPE.value: txn_type}

            for rule_key in [TxnClasses.INBOUND.value, TxnClasses.OUTBOUND.value]:
                if rule_key in info[SmsAttributes.CLASS.value]:
                    info[SmsAttributes.CLASS.value].remove(rule_key)

        if SmsAttributes.CLASS.value in info and RedFlags.CRITICAL_DEFAULT.value in info[SmsAttributes.CLASS.value] \
            and RedFlags.MISSING_PROCESS.value not in info[SmsAttributes.CLASS.value]:
            info[SmsAttributes.CLASS.value].append(RedFlags.MISSING_PROCESS.value)

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

    def _clean_raw_text(self, sms):
        sms = sms.strip().replace("'", "").replace('"', '').replace('val.', 'val. ')\
            .replace('item.', 'item ').replace('item', 'item ').replace('through', ' through')\
            .replace('processed', ' processed').replace('assigned', ' assigned').replace('  ', ' ')
        return sms

    def _determine_highest_probability_match(self, accounts_set, sms):
        def _evaluate_element_weight(elt):
            return len(elt.replace("\s+", "\s").split(' '))

        likely_accts = sorted(accounts_set, key=_evaluate_element_weight)
        prob_acct = None

        for likely_acct in likely_accts:
            prob_acct = self._parse_and_validate_identifier(likely_acct, sms)
            if prob_acct is not None and prob_acct[0].strip() != '':
                break

        return prob_acct

    def _execute_pattern_matching(self, rule_list, sms):
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
                    sys.stderr.write('Could not parse layout rule on line ' + str(i) + " " + rule_str + "\n")

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
                                sys.stderr.write(str(e))

                    if SmsAttributes.ACCOUNT_NO.value in info and info[SmsAttributes.ACCOUNT_NO.value].strip() != '':
                        info[SmsAttributes.ACCOUNT_NO.value] = info[SmsAttributes.ACCOUNT_NO.value].replace(',', '')
                        accounts_set.add(info[SmsAttributes.ACCOUNT_NO.value].strip())

        account_no_exists = True

        if accounts_set is not None and len(accounts_set) > 0:
            (prob_acct_no, prob_acct_type) = self._determine_highest_probability_match(accounts_set, sms)

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

    def _resolve_source_identity(self, sender, bank_mapping):
        if isinstance(bank_mapping, list):
            for item in bank_mapping:
                if str(item['string']).lower() in str(sender).lower():
                    if item['Class'] == 'SourceName':
                        return item['Name']
                    else:
                        return sender[-6:]
            return sender[-6:]