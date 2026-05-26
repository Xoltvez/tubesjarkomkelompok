import socket
import threading
import time
import os

# ============================================================
#  KONFIGURASI
# ============================================================
PROXY_HOST  = '0.0.0.0'
PROXY_PORT  = 8080

SERVER_IP   = '10.190.3.186'   # <-- Ganti dengan IP Laptop A (webserver)
SERVER_PORT = 8000

CACHE_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')

# ============================================================
#  LOGGING
# ============================================================
def log(tag, message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{tag}] {message}")

# ============================================================
#  INISIALISASI CACHE
# ============================================================
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(url_path):
    """Ubah URL path menjadi nama file cache yang aman."""
    safe = url_path.strip('/').replace('/', '_')
    if safe == '':
        safe = 'index.html'
    return os.path.join(CACHE_DIR, safe)

def is_cached(url_path):
    return os.path.isfile(get_cache_path(url_path))

def save_cache(url_path, data):
    try:
        with open(get_cache_path(url_path), 'wb') as f:
            f.write(data)
        log("CACHE", f"Disimpan: {url_path}")
    except Exception as e:
        log("CACHE", f"Gagal simpan cache: {e}")

def load_cache(url_path):
    with open(get_cache_path(url_path), 'rb') as f:
        return f.read()

# ============================================================
#  PARSING HTTP REQUEST
# ============================================================
def parse_request(raw):
    try:
        text  = raw.decode('utf-8', errors='replace')
        lines = text.split('\r\n')
        parts = lines[0].split(' ')
        method = parts[0]
        path   = parts[1] if len(parts) > 1 else '/'
        return method, path
    except Exception as e:
        raise ValueError(f"Gagal parse request: {e}")

# ============================================================
#  FORWARD KE WEBSERVER
# ============================================================
def forward_to_server(raw_request):
    """Kirim request ke webserver dan kembalikan raw response."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((SERVER_IP, SERVER_PORT))
        s.sendall(raw_request)

        response = b''
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()
        return response

    except socket.timeout:
        log("PROXY", f"Timeout saat koneksi ke webserver")
        return build_error(504, "Gateway Timeout", "Webserver tidak merespons.")
    except ConnectionRefusedError:
        log("PROXY", f"Webserver tidak bisa dihubungi ({SERVER_IP}:{SERVER_PORT})")
        return build_error(502, "Bad Gateway", "Tidak bisa terhubung ke webserver.")
    except Exception as e:
        log("PROXY", f"Error forward: {e}")
        return build_error(502, "Bad Gateway", str(e))

def build_error(code, status, detail):
    body = f"<html><body><h1>{code} {status}</h1><p>{detail}</p></body></html>".encode()
    header = (
        f"HTTP/1.1 {code} {status}\r\n"
        f"Content-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    )
    return header.encode() + body

# ============================================================
#  HANDLER TIAP CLIENT (thread terpisah)
# ============================================================
def handle_client(conn, addr):
    log("PROXY", f"Koneksi dari {addr}")
    try:
        raw_request = b''
        conn.settimeout(10)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw_request += chunk
            if b'\r\n\r\n' in raw_request:
                break

        if not raw_request:
            log("PROXY", f"Data kosong dari {addr}")
            return

        # Parse method dan path
        try:
            method, path = parse_request(raw_request)
            log("PROXY", f"{addr} → {method} {path}")
        except ValueError as e:
            log("PROXY", f"Bad request dari {addr}: {e}")
            conn.sendall(build_error(400, "Bad Request", str(e)))
            return

        # Cek cache
        if method == 'GET' and is_cached(path):
            log("CACHE", f"HIT  → {path}")
            response = load_cache(path)
            conn.sendall(response)
            log("PROXY", f"Response dari cache dikirim ke {addr}")
        else:
            log("CACHE", f"MISS → {path}")
            response = forward_to_server(raw_request)

            # Simpan ke cache hanya jika response 200 OK
            if response.startswith(b'HTTP/1.1 200') and method == 'GET':
                save_cache(path, response)

            conn.sendall(response)
            log("PROXY", f"Response dari webserver dikirim ke {addr}")

    except socket.timeout:
        log("PROXY", f"Timeout dari {addr}")
    except Exception as e:
        log("PROXY", f"Error: {e}")
        try:
            conn.sendall(build_error(500, "Internal Server Error", str(e)))
        except:
            pass
    finally:
        conn.close()
        log("PROXY", f"Koneksi ditutup: {addr}")

# ============================================================
#  PROXY SERVER UTAMA
# ============================================================
def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(10)
    log("PROXY", f"Proxy listening di port {PROXY_PORT}")
    log("PROXY", f"Meneruskan request ke {SERVER_IP}:{SERVER_PORT}")
    log("PROXY", f"Cache dir: {CACHE_DIR}")

    while True:
        try:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
            log("PROXY", f"Thread baru untuk {addr} | Aktif: {threading.active_count()}")
        except Exception as e:
            log("PROXY", f"Error accept: {e}")

# ============================================================
#  MAIN
# ============================================================
if __name__ == '__main__':
    log("MAIN", "=== Proxy Server Jaringan Komputer ===")
    start_proxy()
