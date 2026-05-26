import socket
import time
import argparse
import threading

# ============================================================
#  KONFIGURASI
# ============================================================
PROXY_IP    = '10.190.4.22'   # <-- Ganti dengan IP Laptop B (proxy)
PROXY_PORT  = 8080

SERVER_IP   = '10.190.3.186'   # <-- Ganti dengan IP Laptop A (webserver, untuk UDP)
UDP_PORT    = 9000

UDP_PACKETS = 10               # Jumlah paket UDP yang dikirim
UDP_TIMEOUT = 2                # Timeout tiap paket (detik)

# ============================================================
#  LOGGING
# ============================================================
def log(tag, message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{tag}] {message}")

# ============================================================
#  HELPER — Format ukuran bytes
# ============================================================
def format_size(num_bytes):
    """Format bytes ke satuan yang lebih mudah dibaca."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.2f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"

# ============================================================
#  MODE TCP — HTTP GET lewat Proxy
# ============================================================
def tcp_request(path='/index.html'):
    """Kirim HTTP GET ke proxy dan tampilkan response."""
    log("TCP", f"Menghubungi proxy {PROXY_IP}:{PROXY_PORT}")
    log("TCP", f"Meminta path: {path}")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)

        # === Ukur waktu koneksi ===
        t_connect_start = time.time()
        s.connect((PROXY_IP, PROXY_PORT))
        t_connect_end = time.time()
        connect_time = (t_connect_end - t_connect_start) * 1000  # ms

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {PROXY_IP}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        # === Ukur waktu total request-response (TTFB + download) ===
        t_request_start = time.time()
        s.sendall(request.encode())
        log("TCP", "Request terkirim, menunggu response...")

        response = b''
        t_first_byte = None
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            if t_first_byte is None:
                t_first_byte = time.time()  # Catat waktu byte pertama diterima
            response += chunk

        t_request_end = time.time()
        s.close()

        # === Hitung metrik waktu ===
        ttfb          = (t_first_byte - t_request_start) * 1000 if t_first_byte else 0  # ms
        download_time = (t_request_end - (t_first_byte or t_request_start)) * 1000      # ms
        total_time    = (t_request_end - t_request_start) * 1000                        # ms

        # === Hitung ukuran ===
        total_size  = len(response)
        header_size = 0
        body_size   = 0

        # Pisahkan header dan body
        if b'\r\n\r\n' in response:
            header_part, body_part = response.split(b'\r\n\r\n', 1)
            header_size = len(header_part) + 4  # +4 untuk \r\n\r\n
            body_size   = len(body_part)

            headers     = header_part.decode('utf-8', errors='replace')
            body        = body_part.decode('utf-8', errors='replace')

            status_line = headers.split('\r\n')[0]
            log("TCP", f"Status: {status_line}")

            print("\n" + "="*55)
            print("  RESPONSE HEADER:")
            print("="*55)
            print(headers)
            print("="*55)
            print("  RESPONSE BODY:")
            print("="*55)
            print(body)

            # === Ringkasan Performa ===
            print("="*55)
            print("  RINGKASAN PERFORMA")
            print("="*55)
            print(f"  Waktu Koneksi      : {connect_time:.2f} ms")
            print(f"  Time to First Byte : {ttfb:.2f} ms")
            print(f"  Waktu Download     : {download_time:.2f} ms")
            print(f"  Total Waktu        : {total_time:.2f} ms")
            print(f"  ─────────────────────────────────────────")
            print(f"  Ukuran Header      : {format_size(header_size)}")
            print(f"  Ukuran Body        : {format_size(body_size)}")
            print(f"  Total Ukuran       : {format_size(total_size)}")
            print("="*55 + "\n")
        else:
            log("TCP", "Response tidak memiliki body.")
            print(response.decode('utf-8', errors='replace'))
            print(f"\n  Total Ukuran  : {format_size(total_size)}")
            print(f"  Total Waktu   : {total_time:.2f} ms\n")

    except ConnectionRefusedError:
        log("TCP", f"ERROR: Proxy tidak bisa dihubungi di {PROXY_IP}:{PROXY_PORT}")
    except socket.timeout:
        log("TCP", "ERROR: Timeout menunggu response dari proxy")
    except Exception as e:
        log("TCP", f"ERROR: {e}")

# ============================================================
#  MODE UDP — QoS Testing (RTT, Jitter, Packet Loss, Throughput)
# ============================================================
def udp_qos():
    """Kirim paket UDP ke webserver dan hitung statistik QoS."""
    log("UDP", f"Memulai UDP QoS test ke {SERVER_IP}:{UDP_PORT}")
    log("UDP", f"Mengirim {UDP_PACKETS} paket...")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(UDP_TIMEOUT)

    rtt_list      = []
    sent          = 0
    received      = 0
    total_bytes   = 0

    for i in range(1, UDP_PACKETS + 1):
        message = f"PING {i} timestamp={time.time()}"
        payload = message.encode()
        size    = len(payload)

        try:
            t_send = time.time()
            s.sendto(payload, (SERVER_IP, UDP_PORT))
            sent += 1

            data, _ = s.recvfrom(1024)
            t_recv  = time.time()

            rtt = (t_recv - t_send) * 1000  # ms
            rtt_list.append(rtt)
            total_bytes += size
            received += 1

            log("UDP", f"Paket {i}: RTT = {rtt:.3f} ms | Echo: {data.decode('utf-8', errors='replace')}")

        except socket.timeout:
            log("UDP", f"Paket {i}: TIMEOUT (tidak ada echo)")
        except Exception as e:
            log("UDP", f"Paket {i}: ERROR - {e}")

        time.sleep(0.1)  # Jeda antar paket

    s.close()

    # ---- Hitung Statistik ----
    print("\n" + "="*55)
    print("       HASIL QoS UDP")
    print("="*55)
    print(f"  Paket Dikirim   : {sent}")
    print(f"  Paket Diterima  : {received}")

    packet_loss = ((sent - received) / sent * 100) if sent > 0 else 0
    print(f"  Packet Loss     : {packet_loss:.1f}%")

    if rtt_list:
        min_rtt  = min(rtt_list)
        max_rtt  = max(rtt_list)
        avg_rtt  = sum(rtt_list) / len(rtt_list)

        # Jitter = rata-rata selisih RTT antar paket berurutan
        jitter = 0
        if len(rtt_list) > 1:
            diffs  = [abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))]
            jitter = sum(diffs) / len(diffs)

        # Throughput = total byte diterima / total waktu (approx)
        total_time   = (UDP_PACKETS * 0.1)  # detik (jeda 0.1s per paket)
        throughput   = (total_bytes * 8) / total_time  # bit per detik
        throughput_k = throughput / 1000               # kbps

        print(f"  Min RTT         : {min_rtt:.3f} ms")
        print(f"  Avg RTT         : {avg_rtt:.3f} ms")
        print(f"  Max RTT         : {max_rtt:.3f} ms")
        print(f"  Jitter          : {jitter:.3f} ms")
        print(f"  Throughput      : {throughput_k:.2f} kbps")
    else:
        print("  Tidak ada paket yang berhasil diterima.")

    print("="*55 + "\n")

# ============================================================
#  MODE MULTI — Simulasi Banyak Client (multithreading test)
# ============================================================
def multi_client(jumlah=5, path='/index.html'):
    """Jalankan beberapa client sekaligus untuk uji multithreading."""
    log("MULTI", f"Menjalankan {jumlah} client sekaligus...")

    results = {}
    lock    = threading.Lock()

    def worker(client_id):
        log("MULTI", f"Client-{client_id} mulai")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)

            # === Ukur waktu ===
            t_start = time.time()
            s.connect((PROXY_IP, PROXY_PORT))

            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {PROXY_IP}\r\n"
                f"Connection: close\r\n\r\n"
            )
            s.sendall(request.encode())

            response = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                response += chunk
            s.close()

            t_end         = time.time()
            elapsed_ms    = (t_end - t_start) * 1000
            response_size = len(response)

            status = response.split(b'\r\n')[0].decode('utf-8', errors='replace')
            with lock:
                results[client_id] = {
                    'status': status,
                    'time_ms': elapsed_ms,
                    'size': response_size,
                }
            log("MULTI", f"Client-{client_id} selesai → {status} | {elapsed_ms:.2f} ms | {format_size(response_size)}")

        except Exception as e:
            with lock:
                results[client_id] = {'status': f"ERROR: {e}", 'time_ms': 0, 'size': 0}
            log("MULTI", f"Client-{client_id} ERROR: {e}")

    threads = []
    for i in range(1, jumlah + 1):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)

    # Start semua thread hampir bersamaan
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n" + "="*55)
    print("       HASIL MULTI-CLIENT TEST")
    print("="*55)
    print(f"  {'Client':<10} {'Status':<25} {'Waktu':>10} {'Ukuran':>12}")
    print(f"  {'─'*10} {'─'*25} {'─'*10} {'─'*12}")
    for cid, info in sorted(results.items()):
        status   = info['status']
        time_ms  = f"{info['time_ms']:.2f} ms"
        size_str = format_size(info['size'])
        print(f"  Client-{cid:<4} {status:<25} {time_ms:>10} {size_str:>12}")
    print("="*55 + "\n")

# ============================================================
#  MAIN — Argumen CLI
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Client Tubes Jarkom')
    parser.add_argument(
        '--mode',
        choices=['tcp', 'udp', 'multi'],
        required=True,
        help='Mode: tcp (HTTP GET), udp (QoS test), multi (multithreading test)'
    )
    parser.add_argument(
        '--path',
        default='/index.html',
        help='Path yang diminta (untuk mode tcp/multi), default: /index.html'
    )
    parser.add_argument(
        '--clients',
        type=int,
        default=5,
        help='Jumlah client simultan (untuk mode multi), default: 5'
    )

    args = parser.parse_args()

    print("\n" + "="*55)
    print("   CLIENT JARINGAN KOMPUTER")
    print("="*55 + "\n")

    if args.mode == 'tcp':
        tcp_request(path=args.path)
    elif args.mode == 'udp':
        udp_qos()
    elif args.mode == 'multi':
        multi_client(jumlah=args.clients, path=args.path)