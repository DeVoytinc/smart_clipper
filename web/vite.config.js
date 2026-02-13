import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { spawn } from "node:child_process";
import net from "node:net";

function canConnect(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(700);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      resolve(false);
    });
    socket.connect(port, host);
  });
}

function backendAutoStart() {
  let proc = null;

  const spawnBackend = (cmd, args, onError) => {
    proc = spawn(cmd, args, {
      cwd: "..",
      stdio: "inherit",
      shell: false,
      windowsHide: true,
    });
    if (onError) {
      proc.once("error", onError);
    }
    return proc;
  };

  return {
    name: "backend-autostart",
    apply: "serve",
    async configureServer(server) {
      const running = await canConnect(8000);
      if (!running) {
        spawnBackend("python", ["src/web_server.py"], () => {
          if (process.platform === "win32") {
            spawnBackend("py", ["-3", "src/web_server.py"]);
          }
        });
      }

      server.httpServer?.once("close", () => {
        if (proc && !proc.killed) {
          proc.kill();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), backendAutoStart()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/files": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/clips": { target: "http://127.0.0.1:8000", changeOrigin: true },
    }
  },
  build: {
    outDir: "dist",
    emptyOutDir: true
  }
});
