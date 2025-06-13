import requests

def get_deepseek_response(prompt):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": "Bearer sk-6b4d94f9de0e4a8d9fc3ec8690559bc6",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        print(response)
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error: {err}")
    except KeyError:
        print("Unexpected response format")

# Usage
print(get_deepseek_response("Hello"))