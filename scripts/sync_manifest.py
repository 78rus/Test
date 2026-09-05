#!/usr/bin/env python3
"""Embed the local static app files into the Kubernetes ConfigMap manifest."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def config_map_block(filename: str) -> str:
    content = (ROOT / filename).read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"
    lines = (line if not line.strip() else "    " + line for line in content.splitlines(True))
    return f"  {filename}: |\n" + "".join(lines)


manifest = """---
# Касса Control — статический интерфейс операционного центра
apiVersion: v1
kind: ConfigMap
metadata:
  name: simple-web-content
data:
"""
for filename in ("index.html", "styles.css", "app.js"):
    manifest += config_map_block(filename)
manifest += """
---
# Nginx Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simple-web-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: simple-web
  template:
    metadata:
      labels:
        app: simple-web
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
        volumeMounts:
        - name: html-volume
          mountPath: /usr/share/nginx/html
      volumes:
      - name: html-volume
        configMap:
          name: simple-web-content

---
# Сервис для доступа к веб-серверу
apiVersion: v1
kind: Service
metadata:
  name: simple-web-service
spec:
  selector:
    app: simple-web
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
  type: LoadBalancer
"""
(ROOT / "simple-web.yaml").write_text(manifest, encoding="utf-8")
print(f"updated {ROOT / 'simple-web.yaml'}")
