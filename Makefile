ifndef DOCKERIMAGE
DOCKERIMAGE := quay.io/syncano/syncano-platform
endif

SHELL := /bin/bash
GITSHA = $(shell git rev-parse --short HEAD)

.PHONY: help run build pull-staging push-staging build-staging pull-production push-production build-production stop clean test test-with-migrations makemigrations deploy-staging deploy-production encrypt decrypt patch fmt fmtcheck lint
.DEFAULT_GOAL := help
$(VERBOSE).SILENT:

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

guard-%:
	if [ "${${*}}" = "" ]; then \
		echo "Environment variable $* not set"; \
		exit 1; \
	fi

run: build ## Start whole platform locally
	docker-compose up --rm

build: ## Build local platform image (use ./prepare_container.sh to build image for deployment)
	docker-compose build

pull-staging: ## Pull development (staging) platform image
	docker pull $(DOCKERIMAGE):staging || true

push-staging: ## Push staging platform image
	docker tag $(DOCKERIMAGE) $(DOCKERIMAGE):staging
	docker push $(DOCKERIMAGE):staging

build-staging: guard-ACME_EMAIL ## Build development (staging) platform image
	docker build --cache-from $(DOCKERIMAGE):staging -t $(DOCKERIMAGE) --build-arg EMAIL=$(ACME_EMAIL) .

pull-production: ## Pull production platform image
	docker pull $(DOCKERIMAGE):production || true

push-production: ## Push production platform image
	docker tag $(DOCKERIMAGE) $(DOCKERIMAGE):production
	docker push $(DOCKERIMAGE):production

build-production: guard-ACME_EMAIL ## Build production platform image
	docker build --cache-from $(DOCKERIMAGE):production -t $(DOCKERIMAGE) --build-arg EMAIL=$(ACME_EMAIL) --build-arg DEVEL=false .

stop: ## Stop whole platform
	docker-compose stop

clean: stop ## Cleanup repository
	docker-compose rm
	find deploy -name "*.unenc" -delete
	git clean -f

test: ## Run tests in container
	docker-compose run --rm web bash -c "chmod 777 /var/run/docker.sock && su-exec syncano ./test.sh ${ARGS}"

migrate: ## Migrate container database
	docker-compose run --rm web ./run_care.sh

makemigrations: ## Make django migrations
	docker-compose run --rm --no-deps web ./manage.py makemigrations

deploy-staging: ## Deploy application to staging
	echo "=== deploying staging ==="
	kubectl config use-context k8s.syncano.rocks
	./deploy.sh staging stg-$(GITSHA) $(ARGS)

deploy-production: ## Deploy application to production
	echo "=== deploying us1 ==="
	kubectl config use-context k8s.syncano.io
	./deploy.sh us1 prd-$(GITSHA) $(ARGS)

	echo "=== deploying eu1 ==="
	kubectl config use-context gke_pioner-syncano-prod-9cfb_europe-west1_syncano-eu1
	./deploy.sh eu1 prd-$(GITSHA) --no-codebox --skip-push

encrypt: ## Encrypt unencrypted files (for secrets)
	find deploy -name "*.unenc" -exec sh -c 'gpg --batch --yes --passphrase "$(PLATFORM_VAULT_PASS)" --symmetric --cipher-algo AES256 -o "$${1%.unenc}.gpg" "$$1"' _ {} \;

decrypt: ## Decrypt files
	find deploy -name "*.gpg" -exec sh -c 'gpg --batch --yes --passphrase "$(PLATFORM_VAULT_PASS)" --decrypt -o "$${1%.gpg}.unenc" "$$1"' _ {} \;

fmt: ## Format code
	autopep8 . -i

fmtcheck: ## Check code formatting
	autopep8 . -d

lint: ## Run lint checks
	echo "=== lint ==="
	flake8 .
	isort --recursive --check-only .
