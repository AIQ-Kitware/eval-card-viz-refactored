.DEFAULT_GOAL := build

# Optional local settings; command-line make variables take precedence.
-include .env

IMAGE_NAME ?= eval-card-viz:latest
HOST_IP ?= 127.0.0.1
HOST_PORT ?= 8080
CONTAINER_PORT ?= 80
BIND_MOUNTS ?= ./evaluations:/deploy/aiq-evaluations:ro

.PHONY: build serve

build:
	docker build --tag "$(IMAGE_NAME)" .

serve:
	docker run -d --rm --init \
		--publish "$(HOST_IP):$(HOST_PORT):$(CONTAINER_PORT)" \
		$(foreach mount,$(BIND_MOUNTS),--volume "$(mount)") \
		"$(IMAGE_NAME)"
