#!/usr/bin/env bash
set -euo pipefail

PROVIDER="${1:-}"
MODEL_OVERRIDE="${2:-}"
ENV_FILE="${3:-.env}"

if [[ -z "${PROVIDER}" ]]; then
  echo "Usage: scripts/switch_provider.sh <openai|google|openrouter|local> [model] [.env-path]"
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Error: env file not found: ${ENV_FILE}"
  exit 1
fi

case "${PROVIDER}" in
  openai|google|openrouter|local) ;;
  *)
    echo "Error: unsupported provider '${PROVIDER}'"
    echo "Supported: openai, google, openrouter, local"
    exit 1
    ;;
esac

upsert_env() {
  local key="$1"
  local value="$2"
  local file="$3"
  local tmp
  tmp="$(mktemp)"
  awk -v k="${key}" -v v="${value}" '
    BEGIN { updated=0 }
    $0 ~ ("^" k "=") { print k "=" v; updated=1; next }
    { print }
    END { if (updated==0) print k "=" v }
  ' "${file}" > "${tmp}"
  mv "${tmp}" "${file}"
}

normalize_local_url() {
  local raw="$1"
  raw="${raw%/}"
  if [[ -z "${raw}" ]]; then
    echo "http://localhost:11434/v1"
    return
  fi
  if [[ "${raw}" == */v1 ]]; then
    echo "${raw}"
  else
    echo "${raw}/v1"
  fi
}

read_value() {
  local key="$1"
  local file="$2"
  awk -F= -v k="${key}" '$1==k {print substr($0, index($0,$2)); exit}' "${file}"
}

OPENAI_BASE="https://api.openai.com/v1"
GEMINI_BASE="https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE="https://openrouter.ai/api/v1"

case "${PROVIDER}" in
  openai)
    model="${MODEL_OVERRIDE:-$(read_value OPENAI_MODEL "${ENV_FILE}")}"
    model="${model##*/}"
    model="${model:-gpt-4o-mini}"
    upsert_env "LLM_PROVIDER" "openai" "${ENV_FILE}"
    upsert_env "OPENAI_BASE_URL" "${OPENAI_BASE}" "${ENV_FILE}"
    upsert_env "OPENAI_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "EMBEDDING_MODEL" "text-embedding-3-small" "${ENV_FILE}"
    ;;
  google)
    model="${MODEL_OVERRIDE:-$(read_value GOOGLE_MODEL "${ENV_FILE}")}"
    model="${model:-gemini-1.5-pro}"
    upsert_env "LLM_PROVIDER" "google" "${ENV_FILE}"
    upsert_env "OPENAI_BASE_URL" "${GEMINI_BASE}" "${ENV_FILE}"
    upsert_env "GOOGLE_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "OPENAI_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "EMBEDDING_MODEL" "text-embedding-004" "${ENV_FILE}"
    ;;
  openrouter)
    model="${MODEL_OVERRIDE:-$(read_value OPENROUTER_MODEL "${ENV_FILE}")}"
    model="${model:-openai/gpt-4o-mini}"
    if [[ "${model}" != */* ]]; then
      model="openai/${model}"
    fi
    upsert_env "LLM_PROVIDER" "openrouter" "${ENV_FILE}"
    upsert_env "OPENAI_BASE_URL" "${OPENROUTER_BASE}" "${ENV_FILE}"
    upsert_env "OPENROUTER_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "OPENAI_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "EMBEDDING_MODEL" "text-embedding-3-small" "${ENV_FILE}"
    ;;
  local)
    base="$(read_value LOCAL_LLM_BASE_URL "${ENV_FILE}")"
    base="$(normalize_local_url "${base}")"
    model="${MODEL_OVERRIDE:-$(read_value LOCAL_LLM_MODEL "${ENV_FILE}")}"
    model="${model:-gpt-oss:20b}"
    upsert_env "LLM_PROVIDER" "local" "${ENV_FILE}"
    upsert_env "LOCAL_LLM_BASE_URL" "${base}" "${ENV_FILE}"
    upsert_env "LOCAL_LLM_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "OPENAI_BASE_URL" "${base}" "${ENV_FILE}"
    upsert_env "OPENAI_MODEL" "${model}" "${ENV_FILE}"
    upsert_env "EMBEDDING_MODEL" "nomic-embed-text" "${ENV_FILE}"
    ;;
esac

echo "Switched provider -> ${PROVIDER}"
echo "Updated ${ENV_FILE}"
