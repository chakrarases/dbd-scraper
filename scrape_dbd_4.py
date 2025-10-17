import requests
import pandas as pd
from bs4 import BeautifulSoup

# Input and output file paths
input_csv = "input.csv"   # Replace with your input file name
output_csv = "output.csv"

# Read Juristic IDs from CSV
df_input = pd.read_csv(input_csv)
juristic_ids = df_input['Registered No.'].astype(str).tolist()

# Base URL for scraping
base_url = "https://datawarehouse.dbd.go.th/index"

# Prepare list for results
results = []

for juristic_id in juristic_ids:
    # Construct query URL (adjust if API or query params exist)
    params = {'juristicId': juristic_id}  # Example parameter; verify actual site behavior
    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract required fields (update selectors based on actual HTML structure)
        juristic_name = soup.find('span', {'id': 'juristicName'}).get_text(strip=True) if soup.find('span', {'id': 'juristicName'}) else ''
        status = soup.find('span', {'id': 'status'}).get_text(strip=True) if soup.find('span', {'id': 'status'}) else ''
        industry_name = soup.find('span', {'id': 'industryName'}).get_text(strip=True) if soup.find('span', {'id': 'industryName'}) else ''
        registered_capital = soup.find('span', {'id': 'registeredCapital'}).get_text(strip=True) if soup.find('span', {'id': 'registeredCapital'}) else ''
        total_revenue = soup.find('span', {'id': 'totalRevenue'}).get_text(strip=True) if soup.find('span', {'id': 'totalRevenue'}) else ''

        results.append({
            'Registered No.': juristic_id,
            'Juristic Person Name': juristic_name,
            'Status': status,
            'Industry Name': industry_name,
            'Registered Capital (Baht)': registered_capital,
            'Total Revenue (Baht)': total_revenue
        })
    else:
        print(f"Failed to fetch data for ID: {juristic_id}")

# Save results to CSV
df_output = pd.DataFrame(results)
df_output.to_csv(output_csv, index=False)
print(f"Data saved to {output_csv}")