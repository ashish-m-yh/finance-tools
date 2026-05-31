## Usage

python3 sms_test.py <sms filename>

## Purpose

SMS-es are sent by banks and financial institutions.This information can be valuable for financial analytics across different use cases.

## Output

- Generates following attributes from parsed financial SMS -

- amount
- balance
- account no
- red flag signals etc.

Example:

SMS:

042425 is the otp for txn of inr 4095.00 at akbar onli on your equitas debit card ending 0613 valid for 5 mins. please do not share the otp with anyone.

```json
{
    "class": [
        "debit",
        "info"
    ],
    "account": "613",
    "amount": "578",
    "account_type": "debit_card"
}
```

## Files

- Driver file for SMS processing (sms_test.py)
- Rule Engine class (rule_engine.py)
- Rule Configuration Files (rules/*) [this is encrypted as rules.gpg, the rule configurations are proprietary and not FOSS]
