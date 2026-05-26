import socket
import threading
import time
import os

HTTP_HOST = '0.0.0.0'   
HTTP_PORT = 8000        
UDP_HOST  = '0.0.0.0'   
UDP_PORT  = 9000         


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def log(tag, message):
    """Cetak log dengan timestamp dan tag."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{tag}] {message}")


def parse_http_request(raw_data):
    """
    Parse raw HTTP request.
    Return (method, path, headers_dict) atau raise ValueError jika tidak valid.
    """
    try:
        text = raw_data.decode('utf-8', errors='replace')
        lines = text.split('\r\n')
        request_line = lines[0]
        parts = request_line.split(' ')
        if len(parts) < 2:
            raise ValueError("Request line tidak valid")
        method = parts[0]
        path   = parts[1]

        headers = {}
        for line in lines[1:]:
            if ':' in line:
                key, _, value = line.partition(':')
                headers[key.strip()] = value.strip()

        return method, path, headers
    except Exception as e:
        raise ValueError(f"Gagal parse request: {e}")



def read_file(path):
    """
    Baca file dari BASE_DIR berdasarkan URL path.
    Return (content_bytes, mime_type) atau raise FileNotFoundError.
    """

    safe_path = path.lstrip('/')
    if '..' in safe_path:
        raise PermissionError("Path traversal tidak diizinkan")

    
    if safe_path == '' or safe_path == '/':
        safe_path = 'index.html'

    full_path = os.path.join(BASE_DIR, safe_path)

    if not os.path.isfile(full_path):
        raise FileNotFoundError(f"File tidak ditemukan: {safe_path}")


    if safe_path.endswith('.html') or safe_path.endswith('.htm'):
        mime = 'text/html'
    elif safe_path.endswith('.css'):
        mime = 'text/css'
    elif safe_path.endswith('.js'):
        mime = 'application/javascript'
    elif safe_path.endswith('.png'):
        mime = 'image/png'
    elif safe_path.endswith('.jpg') or safe_path.endswith('.jpeg'):
        mime = 'image/jpeg'
    else:
        mime = 'text/plain'

    with open(full_path, 'rb') as f:
        content = f.read()

    return content, mime


def build_response(status_code, status_text, content_type, body_bytes):
    """Bangun raw HTTP response bytes."""
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return header.encode('utf-8') + body_bytes


def response_200(content_type, body_bytes):
    return build_response(200, 'OK', content_type, body_bytes)

def response_404():
    body = b"<html><body><h1>404 Not Found</h1><p>File tidak ditemukan.</p></body></html>"
    return build_response(404, 'Not Found', 'text/html', body)

def response_500(detail=''):
    body = f"<html><body><h1>500 Internal Server Error</h1><p>{detail}</p></body></html>".encode()
    return build_response(500, 'Internal Server Error', 'text/html', body)

def response_400():
    body = b"<html><body><h1>400 Bad Request</h1></body></html>"
    return build_response(400, 'Bad Request', 'text/html', body)


def handle_http_client(conn, addr):
    """Proses satu koneksi HTTP dari proxy."""
    log("HTTP", f"Koneksi diterima dari {addr}")
    try:
        
        raw_data = b''
        conn.settimeout(10)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw_data += chunk
        
            if b'\r\n\r\n' in raw_data:
                break

        if not raw_data:
            log("HTTP", f"Data kosong dari {addr}, koneksi ditutup.")
            return

        try:
            method, path, headers = parse_http_request(raw_data)
            log("HTTP", f"{addr} → {method} {path}")
        except ValueError as e:
            log("HTTP", f"Bad request dari {addr}: {e}")
            conn.sendall(response_400())
            return

        if method != 'GET':
            body = b"<html><body><h1>405 Method Not Allowed</h1></body></html>"
            resp = build_response(405, 'Method Not Allowed', 'text/html', body)
            conn.sendall(resp)
            log("HTTP", f"405 Method Not Allowed untuk {method} {path}")
            return
        try:
            content, mime = read_file(path)
            resp = response_200(mime, content)
            conn.sendall(resp)
            log("HTTP", f"200 OK → {path} ({len(content)} bytes) ke {addr}")

        except FileNotFoundError:
            conn.sendall(response_404())
            log("HTTP", f"404 Not Found → {path} ke {addr}")

        except PermissionError as e:
            conn.sendall(response_403())
            log("HTTP", f"403 Forbidden → {path} ke {addr}: {e}")

        except Exception as e:
            conn.sendall(response_500(str(e)))
            log("HTTP", f"500 Internal Server Error → {path} ke {addr}: {e}")

    except socket.timeout:
        log("HTTP", f"Timeout dari {addr}")
    except Exception as e:
        log("HTTP", f"Error tak terduga dari {addr}: {e}")
        try:
            conn.sendall(response_500(str(e)))
        except:
            pass
    finally:
        conn.close()
        log("HTTP", f"Koneksi ditutup: {addr}")


def start_http_server():
    """Jalankan HTTP server, setiap koneksi di-handle thread baru."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HTTP_HOST, HTTP_PORT))
    server_sock.listen(10)
    log("HTTP", f"HTTP Server berjalan di port {HTTP_PORT}")

    while True:
        try:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=handle_http_client, args=(conn, addr), daemon=True)
            t.start()
            log("HTTP", f"Thread baru untuk {addr} | Total thread aktif: {threading.active_count()}")
        except Exception as e:
            log("HTTP", f"Error saat accept: {e}")

def start_udp_server():
    """
    UDP Echo Server: terima paket dari client, kirim balik (echo).
    Digunakan untuk pengujian QoS (RTT, jitter, packet loss).
    """
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind((UDP_HOST, UDP_PORT))
    log("UDP", f"UDP Echo Server berjalan di port {UDP_PORT}")

    while True:
        try:
            data, addr = udp_sock.recvfrom(1024)
            log("UDP", f"Paket diterima dari {addr}: {data.decode('utf-8', errors='replace')}")
            udp_sock.sendto(data, addr)   # Echo balik
            log("UDP", f"Echo dikirim ke {addr}")
        except Exception as e:
            log("UDP", f"Error: {e}")


def response_403():
    body = b"<html><body><h1>403 Forbidden</h1></body></html>"
    return build_response(403, 'Forbidden', 'text/html', body)


if __name__ == '__main__':
    log("MAIN", "=== Web Server Jaringan Komputer ===")
    log("MAIN", f"Base directory: {BASE_DIR}")

   
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)
    udp_thread.start()

    start_http_server()
