import requests
import json

# Define the API endpoint
url = "https://dataapi.moc.go.th/juristic"

# Set the juristic_id parameter
juristic_id = "0105542065502"  # Replace with your actual juristic ID

# Define the query parameters
params = {
    "juristic_id": juristic_id
}

# Make a GET request to the API with the query parameter
try:
    response = requests.get(url, params=params)
    response.raise_for_status()  # Raise an error for bad status codes
    data = response.json()

    print("API Response:")
    print(json.dumps(data, indent=2, ensure_ascii=False))  # Pretty-print JSON with Thai characters if present

except requests.exceptions.RequestException as e:
    print(f"Error calling API: {e}")