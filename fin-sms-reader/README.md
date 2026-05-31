# Financial SMS Intelligence

Transform raw bank, card, UPI, wallet, and financial SMS messages into structured transaction data.

This project helps fintechs, lenders, accounting platforms, personal finance applications, and enterprises extract actionable financial information from SMS data at scale.

## Typical Use Cases

### Fintech Applications

* Cash flow analysis
* Financial health scoring
* Income verification

### Lending Platforms

* Alternative credit assessment
* Salary verification
* Debt obligation analysis
* Loan eligibility workflows

## Usage

python3 sms_test.py &lt;filename&gt;

## Purpose

SMS-es are sent by banks and financial institutions.This information can be valuable for financial analytics across different use cases.

## What It Does

The Financial SMS Intelligence Engine automatically:

* Parses financial SMS messages from banks and payment providers
* Extracts transaction amounts, balances, dates, merchants and references
* Detects credits, debits, transfers, loan payments, and card transactions
* Normalizes transaction data into a consistent format
* Supports analytics and downstream financial workflows

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

## Consulting & Integration Services

If you're building a fintech, lending platform, accounting solution, or financial analytics product, I offer consulting and implementation services around financial data extraction and transaction intelligence.

## Commercial Support

Organizations requiring:

* Custom integrations
* Enterprise features
* Dedicated support
* Architecture consulting
* Private deployments

can contact me directly.

**Email:** [ashish.mukherjee@gmail.com](mailto:ashish.mukherjee@gmail.com)
**LinkedIn:** https://www.linkedin.com/in/ashishindia/
