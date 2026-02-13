from http.server import ThreadingHTTPServer

from clipserver.http_handler import Handler
from clipserver.settings import HOST, PORT


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Web UI: http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
