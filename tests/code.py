import requests

url = "https://v3.football.api-sports.io/fixtures"

headers = {
    "x-apisports-key": "" 
}

params = {
    "live": "all"
}

try:
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if data.get("errors"):
        print("❌ API Error:", data["errors"])
    else:
        print("✅ Success! Total Live Matches:", data.get("results"))
        if data.get("response"):
            print("📸 Sample Match Snapshot:", data["response"][0]["teams"])
            
except Exception as e:
    print("💥 Connection Error:", e)