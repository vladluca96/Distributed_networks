import requests
import time

URL = 'http://localhost:5000/reverse'
N = 1000  # Number of requests
payload = {'text': 'hello world'}

total_time = 0

for i in range(N):
    start = time.time()
    response = requests.post(URL, json=payload)
    end = time.time()
    total_time += (end - start)

    if i == 0:
        print("Sample response:", response.json())

print(f"Total time for {N} requests: {total_time:.4f} seconds")
print(f"Average time per request: {total_time / N:.6f} seconds")
