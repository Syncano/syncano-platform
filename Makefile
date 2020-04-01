ifndef DOCKERIMAGE
DOCKERIMAGE := syncano/platform
endif

SHELL := /bin/bash
GITSHA = $(shell git rev-parse --short HEAD)

.PHONY: help run build pull-cache push-cache docker build stop clean test test-with-migrations makemigrations deploy-staging deploy-production encrypt decrypt patch fmt fmtcheck lint
.DEFAULT_GOAL := help
$(VERBOSE).SILENT:

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

guard-%:
	if [ "${${*}}" = "" ]; then \
		echo "Environment variable $* not set"; \
		exit 1; \
	fi

require-%:
	if ! hash ${*} 2>/dev/null; then \
		echo "! ${*} not installed"; \
		exit 1; \
	fi

run: require-docker-compose ## Start whole platform locally
	docker-compose up --rm

pull-cache: require-docker ## Pull platform image for cache
	docker pull $(DOCKERIMAGE) || true

push-cache: require-docker ## Push platform image for cache
	docker push $(DOCKERIMAGE)

docker: guard-ACME_EMAIL require-docker ## Build platform image
	docker build --cache-from $(DOCKERIMAGE):latest -t $(DOCKERIMAGE) --build-arg EMAIL=$(ACME_EMAIL) .

build: ## Build platform image for testing (use ./prepare_container.sh to build image for CI)
	docker-compose build

stop: require-docker-compose ## Stop whole platform
	docker-compose stop

clean: stop ## Cleanup repository
	docker-compose rm
	find deploy -name "*.unenc" -delete
	git clean -f

test: require-docker-compose ## Run tests in container
	docker-compose run --rm test bash -c "chmod 777 /var/run/docker.sock && su-exec syncano ./test.sh ${ARGS}"

migrate: require-docker-compose ## Migrate container database
	docker-compose run --rm web ./run_care.sh

makemigrations: require-docker-compose ## Make django migrations
	docker-compose run --rm --no-deps web ./manage.py makemigrations

deploy-staging: require-kubectl ## Deploy application to staging
	echo "=== deploying staging ==="
	kubectl config use-context k8s.syncano.rocks
	./deploy.sh staging $(GITSHA) $(ARGS)

deploy-production: require-kubectl ## Deploy application to production
	echo "=== deploying us1 ==="
	kubectl config use-context k8s.syncano.io
	./deploy.sh us1 $(GITSHA) $(ARGS)

	echo "=== deploying eu1 ==="
	kubectl config use-context gke_pioner-syncano-prod-9cfb_europe-west1_syncano-eu1
	./deploy.sh eu1 $(GITSHA) --no-codebox --skip-push

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
