import os
import json
from anthropic import Anthropic

API_KEY=os.environ['CLAUDE_API_KEY']

client = Anthropic(
    api_key=API_KEY
)

company_data = {
    "company": "Stripe",
    "news": [
        "Stripe expanded operations in Singapore",
        "Stripe hired 200 engineers in AI infrastructure",
        "Stripe partnered with Nvidia for AI payments tooling",
        "Revenue grew 28% YoY"
    ],
    "job_openings": 450,
    "headcount_growth": 18,
    "funding": None
}

prompt = f"""
You are a B2B sales intelligence analyst.

Analyze the following company data and generate structured company signals.

Return JSON with:
- company
- signal_type
- priority (high/medium/low)
- explanation
- recommended_sales_angle

Data:
{json.dumps(company_data, indent=2)}
"""

response = client.messages.create(
    model="claude-sonnet-4-0",
    max_tokens=1000,
    temperature=0.2,
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ]
)

print(response.content[0].text)
