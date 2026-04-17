# Cookbook: Node.js Frontend + nginx

Build a Node.js frontend (React, Vue, Angular, etc.) inside Docker and serve it with nginx — no local Node.js installation required.

---

## What this covers

- `NodeProject` with default `node(20)` builder
- Custom service Dockerfile that copies the build output
- nginx service configuration
- Backend API proxy through nginx

---

## Directory structure

```
my-solution/
├── solution.py
├── assets/
│   └── dockerfiles/
│       └── frontend/
│           ├── Dockerfile        # nginx + copied dist
│           └── nginx.conf        # nginx configuration
```

---

## solution.py

```python
from localbox.models import (
    SolutionConfig,
    NodeProject, node,
    Service, DockerImage, ComposeConfig,
    HttpCheck,
)

config = SolutionConfig(name="myapp")

# ── Project ────────────────────────────────────────────────────────────────────

ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    # output_dir defaults to "dist" — override if your build outputs to "build"
)

# ── Services ───────────────────────────────────────────────────────────────────

frontend = Service(
    name="frontend",
    project=ui,                               # ui build output is a Docker build context
    image=DockerImage(dockerfile="assets/dockerfiles/frontend/Dockerfile"),
    compose=ComposeConfig(
        order=10,
        ports=["80:80"],
        healthcheck=HttpCheck(url="http://localhost:80/"),
    ),
)
```

---

## assets/dockerfiles/frontend/Dockerfile

```dockerfile
# Build stage — runs npm ci && npm run build (via localbox services build)
# The "ui" build context comes from localbox --build-context ui=.build/projects/ui

FROM nginx:alpine

# Copy the compiled frontend from the "ui" project build context
COPY --from=ui dist/ /usr/share/nginx/html/

# Optional: custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

---

## assets/dockerfiles/frontend/nginx.conf

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # SPA routing — serve index.html for all unknown paths
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to the backend
    location /api/ {
        proxy_pass http://api:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Commands

```bash
localbox projects clone
localbox projects build        # runs npm ci && npm run build inside Docker
localbox services build        # builds the nginx image with dist/ copied in
localbox compose generate
docker compose up -d
```

---

## Variations

### Custom Node.js version

```python
from localbox.models import node

ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    builder=node(22),          # Node.js 22
)
```

### Custom build output directory

If your project outputs to `build/` instead of `dist/`:

```python
ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    output_dir="build",        # informational; used in Dockerfile COPY path
)
```

In the Dockerfile:
```dockerfile
COPY --from=ui build/ /usr/share/nginx/html/
```

### Custom build command

If your project uses `yarn` or a different script:

```python
from localbox.models import Builder, DockerImage, CacheVolume

ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    builder=Builder(
        docker_image=DockerImage(name="node-20", image="node:20"),
        build_command="yarn install --frozen-lockfile && yarn build",
        volumes=[CacheVolume(name="yarn", container="/home/node/.yarn")],
        environment={"YARN_CACHE_FOLDER": "/home/node/.yarn"},
    ),
)
```

### Multiple frontends

```python
main_ui = NodeProject("frontend:main", repo="git@github.com:org/main-ui.git")
admin_ui = NodeProject("frontend:admin", repo="git@github.com:org/admin-ui.git")

# Each gets its own service with its own nginx image
main_frontend = Service(
    name="frontend:main",
    project=main_ui,
    image=DockerImage(dockerfile="assets/dockerfiles/main-frontend/Dockerfile"),
    compose=ComposeConfig(order=10, ports=["80:80"]),
)

admin_frontend = Service(
    name="frontend:admin",
    project=admin_ui,
    image=DockerImage(dockerfile="assets/dockerfiles/admin-frontend/Dockerfile"),
    compose=ComposeConfig(order=11, ports=["81:80"]),
)
```

### Frontend + backend in the same nginx

When you want one nginx container that serves both the frontend and proxies the API, use `projects=` to include both build contexts:

```python
gateway = Service(
    name="gateway",
    project=ui,                       # primary: ui dist/
    image=DockerImage(dockerfile="assets/dockerfiles/gateway/Dockerfile"),
    compose=ComposeConfig(
        order=20,
        ports=["80:80"],
        depends_on=[api, db],
    ),
)
```

The gateway Dockerfile can reference both `--from=ui` and any other named contexts.

---

## Working with environment variables at build time

If your Node.js build needs environment variables (e.g. `REACT_APP_API_URL`), pass them through the builder:

```python
from localbox.models import Builder, DockerImage, CacheVolume

ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    builder=Builder(
        docker_image=DockerImage(name="node-20", image="node:20"),
        build_command="npm ci && npm run build",
        volumes=[CacheVolume(name="node", container="/home/node/.npm")],
        environment={
            "npm_config_cache": "/home/node/.npm",
            "REACT_APP_API_URL": "http://localhost:8080",
        },
    ),
)
```
