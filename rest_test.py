import requests
import time
import random
import string
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Process
from flask import Flask, request, jsonify
import statistics
import logging
import pandas as pd
import matplotlib.pyplot as plt
from waitress import serve

# import seaborn as sns

# ---------- PLOTTING ----------
def plot_metric(df, x_col, y_col, group, title, ylabel, filename):
    data = df[df["test_group"] == group].sort_values(x_col)
    plt.figure()
    plt.plot(data[x_col], data[y_col], marker='o')
    plt.title(title)
    plt.xlabel(x_col.replace("_", " ").title())
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.savefig(filename)
# ---------- SERVER CODE ----------
def start_flask_server():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app = Flask(__name__)

    @app.route('/reverse', methods=['POST'])
    def reverse():
        data = request.get_json()
        text = data.get('text', '')
        auth_header = request.headers.get('Authorization')
        session_cookie = request.cookies.get('sessionid')

        # (Optional) Log received metadata
        # print(f"Auth: {auth_header}, Session: {session_cookie}")

        result = text[::-1]
        return jsonify({'result': result})
    # Suppress Waitress queue warnings
    waitress_log = logging.getLogger('waitress.queue')
    waitress_log.setLevel(logging.ERROR)

    # ✅ Serve with Waitress instead of Flask's dev server
    serve(app, host='127.0.0.1', port=5000)

# ---------- TEST DATA ----------
def generate_random_text(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ---------- SINGLE CLIENT TASK ----------
def send_request(session, url, payload):
    headers = {
        'Authorization': 'Bearer dummy_token_12345',
        'X-Custom-Header': 'SomeExtraMetadata'
    }
    cookies = {
        'sessionid': 'fake-session-98765'
    }

    try:
        start = time.time()
        response = session.post(url, json=payload, headers=headers, cookies=cookies, timeout=5)
        elapsed = time.time() - start
        return elapsed, len(json.dumps(payload)), len(response.content), response.status_code
    except Exception:
        return None, 0, 0, 500

# ---------- TEST SCENARIO ----------
def run_test_scenario(num_requests, text_length, num_threads):
    url = 'http://127.0.0.1:5000/reverse'
    times = []
    payload_sizes = []
    response_sizes = []
    errors = 0

    # 🔸 Warm-up requests (not timed)
    with requests.Session() as warm_session:
        for _ in range(20):
            payload = {'text': generate_random_text(text_length)}
            try:
                warm_session.post(url, json=payload, timeout=1)
            except:
                pass

    # Run benchmark
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        with requests.Session() as session:
            futures = [
                executor.submit(send_request, session, url, {'text': generate_random_text(text_length)})
                for _ in range(num_requests)
            ]
            for future in as_completed(futures):
                try:
                    elapsed, payload_size, response_size, status = future.result()
                    if status == 200:
                        times.append(elapsed)
                        payload_sizes.append(payload_size)
                        response_sizes.append(response_size)
                    else:
                        errors += 1
                except Exception:
                    errors += 1

    # Safely calculate statistics
    if times:
        avg_latency = statistics.mean(times)
        min_latency = min(times)
        max_latency = max(times)
        total_duration = sum(times)
        throughput = num_requests / total_duration
        p95 = statistics.quantiles(times, n=100)[94] if len(times) >= 2 else None
    else:
        avg_latency = min_latency = max_latency = throughput = 0
        p95 = None

    print("\n----- Test Scenario -----")
    print(f"Requests: {num_requests}, Text Length: {text_length}, Threads: {num_threads}")
    print(f"Avg Latency: {avg_latency:.6f} sec" if times else "Avg Latency: N/A")
    print(f"Min / Max Latency: {min_latency:.6f} / {max_latency:.6f}" if times else "Min / Max: N/A")
    print(f"95th Percentile Latency: {p95:.6f}" if p95 is not None else "95th Percentile: N/A")
    print(f"Errors: {errors}")
    print(f"Avg Payload Size: {statistics.mean(payload_sizes):.2f} bytes" if payload_sizes else "Avg Payload Size: N/A")
    print(f"Avg Response Size: {statistics.mean(response_sizes):.2f} bytes" if response_sizes else "Avg Response Size: N/A")

    return {
        "requests": num_requests,
        "text_length": text_length,
        "threads": num_threads,
        "avg_latency": avg_latency,
        "min_latency": min_latency,
        "max_latency": max_latency,
        "p95_latency": p95,
        "errors": errors,
        "throughput_rps": throughput
    }

def averaged_run_test_scenario(num_runs, **kwargs):
    runs = [run_test_scenario(**kwargs) for _ in range(num_runs)]
    averaged_result = {}

    for key in runs[0]:
        values = [r[key] for r in runs if isinstance(r[key], (int, float))]
        if values:
            averaged_result[key] = sum(values) / len(values)
        else:
            averaged_result[key] = None if key == "p95_latency" else 0  # p95 can stay None, others default to 0

    return averaged_result

# ---------- MAIN ----------
if __name__ == '__main__':
    print("Starting Flask server...")
    server_process = Process(target=start_flask_server)
    server_process.start()
    time.sleep(2)  # wait for server to start

    try:
        results = []

        num_runs = 10  # Number of times to average each scenario

        # 🔹 Test A: Vary Payload Size (keep threads & requests fixed)
        for size in [10, 100, 500, 1000, 2000]:
            result = averaged_run_test_scenario(num_runs, num_requests=500, text_length=size, num_threads=10)
            result["test_group"] = "Payload Size"
            results.append(result)

        # 🔹 Test B: Vary Thread Count (keep text & requests fixed)
        for threads in [1, 5, 10, 20, 50, 100]:
            result = averaged_run_test_scenario(num_runs, num_requests=500, text_length=200, num_threads=threads)
            result["test_group"] = "Concurrency"
            results.append(result)

        # 🔹 Test C: Vary Request Volume (keep text & threads fixed)
        for reqs in [100, 500, 1000, 2000, 3000]:
            result = averaged_run_test_scenario(num_runs, num_requests=reqs, text_length=200, num_threads=20)
            result["test_group"] = "Request Volume"
            results.append(result)

        # Convert to DataFrame
        df = pd.DataFrame(results)
        df.to_csv("rest_test_results.csv", index=False)

        # ---------- PLOTTING ----------
        plt.figure()
        df[df["test_group"] == "Payload Size"].sort_values("text_length") \
            .plot(x="text_length", y="avg_latency", marker='o', title="Avg Latency vs Payload Size")
        plt.ylabel("Latency (sec)")
        plt.grid(True)
        plt.savefig("latency_vs_payload.png")

        plt.figure()
        df[df["test_group"] == "Concurrency"].sort_values("threads") \
            .plot(x="threads", y="avg_latency", marker='o', title="Avg Latency vs Thread Count")
        plt.ylabel("Latency (sec)")
        plt.grid(True)
        plt.savefig("latency_vs_threads.png")

        plt.figure()
        df[df["test_group"] == "Request Volume"].sort_values("requests") \
            .plot(x="requests", y="avg_latency", marker='o', title="Avg Latency vs Total Requests")
        plt.ylabel("Latency (sec)")
        plt.grid(True)
        plt.savefig("latency_vs_requests.png")

        # Plot: 95th percentile latency vs payload size
        plt.figure()
        df[df["test_group"] == "Payload Size"].sort_values("text_length") \
            .plot(x="text_length", y="p95_latency", marker='o', title="95th Percentile Latency vs Payload Size")
        plt.ylabel("Latency (sec)")
        plt.grid(True)
        plt.savefig("p95_latency_vs_payload.png")

        # Plot: Throughput vs thread count
        plt.figure()
        df[df["test_group"] == "Concurrency"].sort_values("threads") \
            .plot(x="threads", y="throughput_rps", marker='o', title="Throughput vs Thread Count")
        plt.ylabel("Requests per second")
        plt.grid(True)
        plt.savefig("throughput_vs_threads.png")

        plt.show()

        
        # ---------- PLOTS ----------
        plot_metric(df, "text_length", "avg_latency", "Payload Size", "REST - Avg Latency vs Payload Size", "Latency (sec)", "rest_latency_vs_payload.png")
        plot_metric(df, "threads", "avg_latency", "Concurrency", "REST - Avg Latency vs Threads", "Latency (sec)", "rest_latency_vs_threads.png")
        plot_metric(df, "requests", "avg_latency", "Request Volume", "REST - Avg Latency vs Requests", "Latency (sec)", "rest_latency_vs_requests.png")
        plot_metric(df, "text_length", "p95_latency", "Payload Size", "REST - 95th Percentile Latency", "Latency (sec)", "rest_p95_latency.png")
        plot_metric(df, "threads", "throughput_rps", "Concurrency", "REST - Throughput vs Threads", "Requests/sec", "rest_throughput_vs_threads.png")
        plot_metric(df, "requests", "throughput_rps", "Request Volume", "REST - Throughput vs Requests", "Requests/sec", "rest_throughput_vs_requests.png")

    finally:
        print("Shutting down server...")
        server_process.terminate()
        server_process.join()
