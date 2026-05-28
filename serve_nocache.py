#!/usr/bin/env python3
import http.server
import sys
import os

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # ログ出力を抑制

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    directory = sys.argv[2] if len(sys.argv) > 2 else '.'
    os.chdir(directory)
    with http.server.HTTPServer(('', port), NoCacheHandler) as httpd:
        print(f'Serving on http://localhost:{port}/ (no-cache)')
        httpd.serve_forever()
