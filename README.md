# Docker instructions

Build image:

```bash
docker build -t mommy-app .
```

Run container (detached):

```bash
docker run -d --name mommy -e DISPLAY=host.docker.internal:0 -v "%cd%":/app mommy-app
```

Using docker-compose:

```bash
docker compose up --build
```

Notes:
- This project uses GUI libraries (`pygame`, `customtkinter`). On Windows run an X server (e.g. VcXsrv) and set `DISPLAY` to `host.docker.internal:0`.
- If you don't need GUI, replace the `CMD` in `Dockerfile` with `python 1212.py`.
