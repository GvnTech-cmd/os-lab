SHELL := /bin/bash
.DEFAULT_GOAL := help

FRIDA ?= $(if $(wildcard .venv/bin/frida),.venv/bin/frida,frida)
LABCTL ?= ../../labctl

.PHONY: pinning help setup setup-python platform-tools preflight pull up boot static-up static-down down status monitor profiles logs adb shell install wf1 wf2 hook report install-service uninstall-service clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Ubuntu Server host setup: KVM, Docker, adb, groups, dirs (needs sudo)
	sudo bash scripts/setup-ubuntu.sh

setup-python: ## Create .venv and install requirements.txt
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

platform-tools: ## Download Google's adb/fastboot into tools/platform-tools (not shipped in the repo)
	python3 scripts/get_platform_tools.py

preflight: ## Check OS / KVM / docker / ports / disk (cheat sheet §0)
	bash scripts/preflight.sh

pull: ## Pull the container images
	docker compose pull

static-up: ## Start only the KVM-free services: mobsf, mitmproxy, tools
	docker compose -f docker-compose.win.yml up -d mobsf mitmproxy tools

static-down: ## Stop the KVM-free stack
	docker compose -f docker-compose.win.yml down

up: ## Start all services using the active .env mode (without waiting)
	@if [ -x "$(LABCTL)" ]; then "$(LABCTL)" android start; else docker compose up -d; fi

boot: ## Start services and wait until the emulator is ready
	@if [ -x "$(LABCTL)" ]; then "$(LABCTL)" android start --wait; else docker compose up -d && bash scripts/wait-boot.sh; fi

down: ## Stop the stack (dynamic or static)
	@if [ -x "$(LABCTL)" ]; then "$(LABCTL)" android stop; else docker compose down; fi

status: ## Service status + emulator readiness
	@if [ -x "$(LABCTL)" ]; then "$(LABCTL)" android status; else docker compose ps && docker compose exec -T android cat device_status; fi

monitor: ## Live dashboard: state, endpoints, CPU/RAM, artifacts
	../../labctl android monitor

profiles: ## List management profiles (lightweight/development/performance)
	../../labctl android profiles

logs: ## Follow emulator container logs
	docker compose logs -f android

adb: ## Interactive shell on the emulator
	docker compose exec android adb shell

shell: ## Shell inside the tools container (jadx, apktool, radare2)
	docker compose exec tools bash

install: ## Install an APK into the emulator: make install APK=path/to/app.apk
	@test -n "$(APK)" || { echo "usage: make install APK=path/to/app.apk"; exit 1; }
	@mkdir -p apks && cp "$(APK)" apks/
	docker compose exec -T android adb install -r "/apks/$(notdir $(APK))"

wf1: ## WF1 static: MobSF scan → JADX decompile → report. make wf1 APK=app.apk
	@test -n "$(APK)" || { echo "usage: make wf1 APK=path/to/app.apk"; exit 1; }
	bash scripts/wf1-static.sh "$(APK)"

wf2: ## WF2 dynamic: boot → deploy → mitmproxy → frida (optional). make wf2 APK=app.apk [PKG=com.example]
	bash scripts/wf2-dynamic.sh $(APK) $(PKG)

pinning: ## PENT-11 static SSL-pinning classifier (no device needed): make pinning APK=app.apk
	@test -n "$(APK)" || { echo "usage: make pinning APK=path/to/app.apk"; exit 1; }
	python3 scripts/pinning_detector.py "$(APK)"

hook: ## Run a Frida hook against a running app: make hook PKG=com.example HOOK=hooks/ssl-pinning-bypass.js
	@test -n "$(PKG)" && test -n "$(HOOK)" || { echo "usage: make hook PKG=com.example HOOK=hooks/ssl-pinning-bypass.js"; exit 1; }
	$(FRIDA) -U -f "$(PKG)" -l "$(HOOK)" --no-pause

report: ## Collect logs, device status and flows into artifacts/
	bash scripts/report.sh

install-service: ## Install a systemd unit that starts the stack at boot
	sudo bash scripts/install-service.sh

uninstall-service: ## Remove the systemd unit
	sudo bash scripts/uninstall-service.sh

clean: ## Remove all artifacts (keeps the directory)
	find artifacts -mindepth 1 ! -name .gitkeep -delete
