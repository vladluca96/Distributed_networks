import time
import random
import string
import statistics
import logging
import pandas as pd
import matplotlib.pyplot as plt
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import ServerProxy
from multiprocessing import Process
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- SERVER CODE ----------
def start_xmlrpc_server():
    logging.getLogger("xmlrpc.server").setLevel(logging.ERROR)
    server = SimpleXMLRPCServer(("127.0.0.1", 8000), allow_none=True, logRequests=False)

    def reverse_text(text):
        return text[::-1]

    server.register_function(reverse_text, "reverse_text")
    server.serve_forever()

# ---------- TEST DATA ----------
def generate_random_text(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ---------- SINGLE CLIENT TASK ----------
def send_xmlrpc_request(text):
    try:
        proxy = ServerProxy("http://127.0.0.1:8000", allow_none=True)
        start = time.time()
        result = proxy.reverse_text(text)
        elapsed = time.time() - start
        return elapsed, len(text), len(result), 200
    except Exception:
        return None, 0, 0, 500

# ---------- TEST SCENARIO ----------
def run_test_scenario(num_requests, text_length, num_threads):
    times = []
    payload_sizes = []
    response_sizes = []
    errors = 0

    # 🔸 Warm-up
    for _ in range(20):
        try:
            send_xmlrpc_request(generate_random_text(text_length))
        except:
            pass

    # 🔸 Benchmark
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(send_xmlrpc_request, generate_random_text(text_length))
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
            except:
                errors += 1

    # 🔸 Metrics
    if times:
        avg_latency = statistics.mean(times)
        min_latency = min(times)
        max_latency = max(times)
        p95 = statistics.quantiles(times, n=100)[94] if len(times) >= 2 else None
        throughput = num_requests / sum(times)
    else:
        avg_latency = min_latency = max_latency = throughput = 0
        p95 = None

    print("\n----- Test Scenario -----")
    print(f"Requests: {num_requests}, Text Length: {text_length}, Threads: {num_threads}")
    print(f"Avg Latency: {avg_latency:.6f} sec" if times else "Avg Latency: N/A")
    print(f"Min / Max Latency: {min_latency:.6f} / {max_latency:.6f}" if times else "Min / Max: N/A")
    print(f"95th Percentile Latency: {p95:.6f}" if p95 else "95th Percentile: N/A")
    print(f"Errors: {errors}")
    print(f"Avg Payload Size: {statistics.mean(payload_sizes):.2f} bytes" if payload_sizes else "Payload Size: N/A")
    print(f"Avg Response Size: {statistics.mean(response_sizes):.2f} bytes" if response_sizes else "Response Size: N/A")

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

# ---------- AVERAGING ----------
def averaged_run_test_scenario(num_runs, **kwargs):
    runs = [run_test_scenario(**kwargs) for _ in range(num_runs)]
    averaged_result = {}
    for key in runs[0]:
        values = [r[key] for r in runs if isinstance(r[key], (int, float))]
        averaged_result[key] = sum(values) / len(values) if values else (None if 'p95' in key else 0)
    return averaged_result

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

# ---------- MAIN ----------
if __name__ == '__main__':
    print("Starting XML-RPC server...")
    server_process = Process(target=start_xmlrpc_server)
    server_process.start()
    time.sleep(2)

    try:
        results = []
        num_runs = 5

        for size in [10, 100, 500, 1000, 2000]:
            result = averaged_run_test_scenario(num_runs, num_requests=500, text_length=size, num_threads=10)
            result["test_group"] = "Payload Size"
            results.append(result)

        for threads in [1, 5, 10, 20, 50, 100]:
            result = averaged_run_test_scenario(num_runs, num_requests=500, text_length=200, num_threads=threads)
            result["test_group"] = "Concurrency"
            results.append(result)

        for reqs in [100, 500, 1000, 2000, 3000]:
            result = averaged_run_test_scenario(num_runs, num_requests=reqs, text_length=200, num_threads=20)
            result["test_group"] = "Request Volume"
            results.append(result)

        df = pd.DataFrame(results)
        df.to_csv("xmlrpc_test_results.csv", index=False)

                # ---------- PRINT FORMATTED RESULTS ----------
        pd.set_option("display.float_format", "{:.4f}".format)
        for group in ["Payload Size", "Concurrency", "Request Volume"]:
            print(f"\n===== Summary: {group} =====")
            subset = df[df["test_group"] == group]
            if group == "Payload Size":
                display_cols = ["text_length", "avg_latency", "p95_latency", "throughput_rps", "errors"]
            elif group == "Concurrency":
                display_cols = ["threads", "avg_latency", "p95_latency", "throughput_rps", "errors"]
            elif group == "Request Volume":
                display_cols = ["requests", "avg_latency", "p95_latency", "throughput_rps", "errors"]
            print(subset[display_cols].to_string(index=False))


        # ---------- PLOTS ----------
        plot_metric(df, "text_length", "avg_latency", "Payload Size", "XML-RPC - Avg Latency vs Payload Size", "Latency (sec)", "xmlrpc_latency_vs_payload.png")
        plot_metric(df, "threads", "avg_latency", "Concurrency", "XML-RPC - Avg Latency vs Threads", "Latency (sec)", "xmlrpc_latency_vs_threads.png")
        plot_metric(df, "requests", "avg_latency", "Request Volume", "XML-RPC - Avg Latency vs Requests", "Latency (sec)", "xmlrpc_latency_vs_requests.png")
        plot_metric(df, "text_length", "p95_latency", "Payload Size", "XML-RPC - 95th Percentile Latency", "Latency (sec)", "xmlrpc_p95_latency.png")
        plot_metric(df, "threads", "throughput_rps", "Concurrency", "XML-RPC - Throughput vs Threads", "Requests/sec", "xmlrpc_throughput_vs_threads.png")
        plot_metric(df, "requests", "throughput_rps", "Request Volume", "XML-RPC - Throughput vs Requests", "Requests/sec", "xmlrpc_throughput_vs_requests.png")

        plt.show()

    finally:
        print("Shutting down XML-RPC server...")
        server_process.terminate()
        server_process.join()
