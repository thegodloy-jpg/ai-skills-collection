#!/bin/bash
set -euo pipefail

TEST_IP=127.0.0.1
BASE_URL="http://127.0.0.1:18000"
TEMPERATURE=0
REQUEST_RATE=""
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WARMUPS_NUM=5
SLA_MODE_NAME="sla-turning-point"
SLA_TTFT_TARGET_MS=8000
SLA_TPOT_TARGET_MS=50
SLA_TTFT_KNEE_MS=5000
SLA_TPOT_KNEE_MS=50
SLA_TTFT_BREAK_MS=8000
SLA_TPOT_BREAK_MS=60
CURRENT_SLA_TTFT_TARGET_MS="$SLA_TTFT_TARGET_MS"
CURRENT_SLA_TPOT_TARGET_MS="$SLA_TPOT_TARGET_MS"
CURRENT_SLA_TTFT_KNEE_MS="$SLA_TTFT_KNEE_MS"
CURRENT_SLA_TPOT_KNEE_MS="$SLA_TPOT_KNEE_MS"
CURRENT_SLA_TTFT_BREAK_MS="$SLA_TTFT_BREAK_MS"
CURRENT_SLA_TPOT_BREAK_MS="$SLA_TPOT_BREAK_MS"
# 每次 vllm bench serve 开始前，是否调用服务端 /reset_prefix_cache 清空 prefix cache（默认开启，可用 --no-reset-prefix-cache 关闭）
PREFIX_CACHE_RESET="${PREFIX_CACHE_RESET:-true}"
ACCELERATOR_TYPE=""
CURRENT_ACCELERATOR_TYPE="nvidia"
SPECULATIVE_INFERENCE_ENABLED=false
INPUT_LEN_ARG=""
OUTPUT_LEN_ARG=""
NUM_PROMPTS_ARG=""
MAX_CONCURRENCY_ARG=""
PREFIX_RATE_ARG=""
declare -a SLA_EXPANSION_CONCURRENCIES=(12 16 24 32 48 64 96 128 192 256 288 320 352 384 416 448 480 512)
declare -a SLA_SCENARIOS=(
    "2048|2048|对话|0.0"
    "8192|1024|通用复杂任务|0.0"
    "16384|4096|合同分析|0.0"
    "65536|1024|Agent应用|0.9"
    "131072|1024|AI Coding|0.9"
    "1024000|1024|特长上下文|0.99"
)

# SLA 模式下仅在以下场景执行 prefix cache 清空（逗号分隔，默认 对话/通用复杂任务/合同分析；可用 --sla-reset-scenarios 覆盖）
SLA_RESET_PREFIX_SCENARIOS_STR="${SLA_RESET_PREFIX_SCENARIOS_STR:-对话,通用复杂任务,合同分析}"
declare -a PREFIX_CACHE_RESET_SCENARIOS=()

#input_len output_len num_prompts max_concurrency repeat_rate
declare -a combinations=(
     "1024 1024 640 128 0.0"
     "2048 2048 389 98 0.6"
     "3500 1500 330 66 0.7"
#     "4096 1024 300 60 0.8"
#     "8192 1024 150 30 0.6"
#     "16384 1024 75 15 0.9"
#     "32768 1024 35 7 0"
#     "65536 1024 40 2 0.9"
#     "131072 1024 40 2 0.99"
)

CUSTOM_COMBINATIONS=()

generate_combo_dirs() {
    local combo_dirs=()
    for combo in "${combinations[@]}"; do
        read input_len output_len num_prompts max_concurrency repeat_rate <<< "$combo"
        combo_dirs+=("$(get_combo_dir_name "$input_len" "$output_len" "$num_prompts" "$max_concurrency" "${repeat_rate:-}")")
    done
    echo "${combo_dirs[@]}"
}

log() {
    local message="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message"
}

get_combo_dir_name() {
    local input_len="$1"
    local output_len="$2"
    local num_prompts="$3"
    local max_concurrency="$4"
    local repeat_rate="${5:-}"
    local dir_name="in${input_len}_out${output_len}_prompts${num_prompts}_conc${max_concurrency}"
    if [[ -n "$repeat_rate" ]] && awk -v rate="$repeat_rate" 'BEGIN { exit !(rate > 0) }'; then
        dir_name="${dir_name}_pr${repeat_rate}"
    fi
    echo "$dir_name"
}

get_sla_combo_dir_name() {
    local scenario_id="$1"
    local input_len="$2"
    local output_len="$3"
    local num_prompts="$4"
    local max_concurrency="$5"
    echo "${scenario_id}_in${input_len}_out${output_len}_prompts${num_prompts}_conc${max_concurrency}"
}

resolve_default_dataset_name() {
    if [[ "$SPECULATIVE_INFERENCE_ENABLED" == true ]]; then
        echo "speed_bench"
    elif [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        echo "random"
    elif [[ "$MODEL_NAME" == "Qwen3-VL-32B-Instruct" || "$MODEL_NAME" == "Qwen_Qwen3-VL-30B-A3B-Instruct" ]]; then
        echo "random--mm"
    else
        echo "random"
    fi
}

extract_dataset_path_from_args() {
    local dataset_path=""

    if [[ -n "${DATASET_ARGS:-}" && "$DATASET_ARGS" =~ --dataset-path[[:space:]=]+([^[:space:]]+) ]]; then
        dataset_path="${BASH_REMATCH[1]}"
        dataset_path="${dataset_path%\"}"
        dataset_path="${dataset_path#\"}"
        dataset_path="${dataset_path%\'}"
        dataset_path="${dataset_path#\'}"
    fi

    echo "$dataset_path"
}

calculate_num_prompts() {
    local input_len="$1"
    local output_len="$2"
    local max_concurrency="$3"
    local total_len=$((input_len + output_len))
    local num_prompts
    if (( total_len <= 32768 )); then
        num_prompts=$((max_concurrency * 5))
    else
        num_prompts=$((max_concurrency * 4))
    fi
    
    echo "$num_prompts"
}

calculate_num_prompts_old() {
    local input_len="$1"
    local output_len="$2"
    local max_concurrency="$3"
    local total_len=$((input_len + output_len))
    local num_prompts

    if (( total_len <= 4096 )); then
        num_prompts=$((max_concurrency * 4))
        (( num_prompts < 32 )) && num_prompts=32
    elif (( total_len <= 32768 )); then
        num_prompts=$((max_concurrency * 3))
        (( num_prompts < 16 )) && num_prompts=16
    elif (( total_len <= 131072 )); then
        num_prompts=$((max_concurrency * 2))
        (( num_prompts < 8 )) && num_prompts=8
    else
        num_prompts=$((max_concurrency * 2))
        (( num_prompts < 6 )) && num_prompts=6
    fi

    echo "$num_prompts"
}

extract_json_value() {
    local file="$1"
    local key="$2"
    sed -n 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$file" | head -1
}

clean_number() {
    local value="$1"
    echo "$value" | sed 's/[^0-9.]//g' | grep -E '^[0-9]+\.?[0-9]*$' || echo "0"
}

resolve_prefix_ratio() {
    local input_len="$1"
    local repeat_rate="${2:-}"
    local prefix_len=""

    if [[ -n "$repeat_rate" ]]; then
        echo "$repeat_rate"
        return 0
    fi

    if [[ -n "${PREFIX_RATE_ARG:-}" ]]; then
        echo "$PREFIX_RATE_ARG"
        return 0
    fi

    if [[ -n "${DATASET_ARGS:-}" && "$DATASET_ARGS" =~ --prefix[-_]rate[[:space:]=]+([0-9.]+) ]]; then
        echo "${BASH_REMATCH[1]}"
        return 0
    fi

    if [[ -n "${DATASET_ARGS:-}" && "$DATASET_ARGS" =~ --random-prefix-len[[:space:]=]+([0-9]+) ]]; then
        prefix_len="${BASH_REMATCH[1]}"
        awk -v prefix_len="$prefix_len" -v input_len="$input_len" 'BEGIN {
            if (input_len <= 0) {
                print "0"
            } else {
                printf "%.6f", prefix_len / input_len
            }
        }'
        return 0
    fi

    echo "0"
}

resolve_output_start() {
    local output_len="$1"
    local range_ratio="0"

    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        echo "$output_len"
        return 0
    fi

    if [[ -n "${DATASET_ARGS:-}" && "$DATASET_ARGS" =~ --random-range-ratio[[:space:]=]+([0-9.]+) ]]; then
        range_ratio="${BASH_REMATCH[1]}"
    fi

    awk -v output_len="$output_len" -v range_ratio="$range_ratio" 'BEGIN {
        value = int(output_len * (1 - range_ratio))
        if (value < 0) {
            value = 0
        }
        print value
    }'
}

resolve_request_rate() {
    if [[ -n "$REQUEST_RATE" ]]; then
        echo "$REQUEST_RATE"
    else
        echo "inf"
    fi
}

detect_accelerator_type() {
    if [[ -n "$ACCELERATOR_TYPE" ]]; then
        echo "$ACCELERATOR_TYPE"
        return 0
    fi

    if command -v npu-smi >/dev/null 2>&1 || command -v npu-smi-info >/dev/null 2>&1; then
        echo "ascend"
    elif command -v nvidia-smi >/dev/null 2>&1; then
        echo "nvidia"
    else
        echo "nvidia"
    fi
}

set_current_sla_thresholds() {
    local input_len="$1"
    local output_len="$2"
    local scenario_name="$3"
    local repeat_rate="$4"
    local ttft_target_ms="$SLA_TTFT_BREAK_MS"
    local tpot_target_ms="$SLA_TPOT_BREAK_MS"

    CURRENT_SLA_TTFT_KNEE_MS="$SLA_TTFT_KNEE_MS"
    CURRENT_SLA_TPOT_KNEE_MS="$SLA_TPOT_KNEE_MS"
    CURRENT_SLA_TTFT_BREAK_MS="$SLA_TTFT_BREAK_MS"
    CURRENT_SLA_TPOT_BREAK_MS="$SLA_TPOT_BREAK_MS"
    CURRENT_ACCELERATOR_TYPE=$(detect_accelerator_type)

    case "${input_len}|${output_len}|${scenario_name}|${repeat_rate}" in
        "2048|2048|对话|0.0")
            ttft_target_ms=8000
            tpot_target_ms=60
            ;;
        "8192|1024|通用复杂任务|0.0")
            ttft_target_ms=12000
            tpot_target_ms=60
            ;;
        "16384|4096|合同分析|0.0")
            ttft_target_ms=15000
            tpot_target_ms=60
            ;;
        "65536|1024|Agent应用|0.9")
            ttft_target_ms=30000
            tpot_target_ms=120
            ;;
        "131072|1024|AI Coding|0.9")
            ttft_target_ms=30000
            tpot_target_ms=120
            ;;
        "1024000|1024|特长上下文|0.99")
            ttft_target_ms=30000
            tpot_target_ms=120
            ;;
    esac

    CURRENT_SLA_TTFT_KNEE_MS="$ttft_target_ms"
    CURRENT_SLA_TTFT_BREAK_MS="$ttft_target_ms"
    CURRENT_SLA_TPOT_KNEE_MS="$tpot_target_ms"
    CURRENT_SLA_TPOT_BREAK_MS="$tpot_target_ms"
    CURRENT_SLA_TTFT_TARGET_MS="$ttft_target_ms"
    CURRENT_SLA_TPOT_TARGET_MS="$tpot_target_ms"
}

classify_sla_state() {
    local ttft_ms="$1"
    local tpot_ms="$2"
    awk -v ttft="$ttft_ms" -v tpot="$tpot_ms" \
        -v ttft_knee="$CURRENT_SLA_TTFT_KNEE_MS" -v tpot_knee="$CURRENT_SLA_TPOT_KNEE_MS" \
        -v ttft_break="$CURRENT_SLA_TTFT_BREAK_MS" -v tpot_break="$CURRENT_SLA_TPOT_BREAK_MS" 'BEGIN {
        if (ttft <= ttft_knee && tpot <= tpot_knee) {
            print "SAFE"
        } else if (ttft > ttft_break || tpot > tpot_break) {
            print "BREAK"
        } else {
            print "KNEE"
        }
    }'
}

compare_metric_to_sla() {
    local metric_value="$1"
    local sla_value="$2"
    awk -v metric="$metric_value" -v sla="$sla_value" 'BEGIN {
        if (metric >= sla) {
            print "REACHED"
        } else {
            print "NOT_REACHED"
        }
    }'
}

combine_sla_metric_status() {
    local ttft_status="$1"
    local tpot_status="$2"

    if [[ "$ttft_status" == "REACHED" || "$tpot_status" == "REACHED" ]]; then
        echo "REACHED"
    else
        echo "NOT_REACHED"
    fi
}

write_csv_header() {
    local file_path="$1"
    local header_line="$2"
    printf '\xEF\xBB\xBF%s\n' "$header_line" > "$file_path"
}

append_sorted_core_metrics_row() {
    local row="$1"
    local temp_file="${CORE_METRICS_CSV}.tmp"
    local data_dir="${CORE_METRICS_CSV}.sort.d"
    local line
    local scenario_name
    local scenario_idx
    local idx
    local -A scenario_index_map=()
    local -a scenario_order=()

    rm -rf "$data_dir"
    mkdir -p "$data_dir"

    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        scenario_name="${line%%,*}"
        if [[ -z "${scenario_index_map[$scenario_name]+x}" ]]; then
            scenario_idx="${#scenario_order[@]}"
            scenario_order+=("$scenario_name")
            scenario_index_map["$scenario_name"]="$scenario_idx"
            : > "$data_dir/${scenario_idx}.csv"
        fi
        printf '%s\n' "$line" >> "$data_dir/${scenario_index_map[$scenario_name]}.csv"
    done < <(
        {
            tail -n +2 "$CORE_METRICS_CSV" 2>/dev/null || true
            printf '%s\n' "$row"
        }
    )

    head -n 1 "$CORE_METRICS_CSV" > "$temp_file"
    for idx in "${!scenario_order[@]}"; do
        LC_ALL=C sort -s -t',' -k5,5n "$data_dir/${idx}.csv" >> "$temp_file"
    done

    mv "$temp_file" "$CORE_METRICS_CSV"
    rm -rf "$data_dir"
}

init_metrics_files() {
    CORE_METRICS_CSV="$RESULTS_DIR/core_metrics.csv"
    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        SLA_RESULTS_CSV="$RESULTS_DIR/sla_search_results.csv"
        write_csv_header "$CORE_METRICS_CSV" "scenario_name,input_length,output_length,request_rate,max_concurrency,num_prompts,total_input_len,prefix_ratio,output_start,duration,failed_requests,request_throughput,output_token_throughput,total_token_throughput,mean_ttft,p90_ttft,p95_ttft,p99_ttft,mean_tpot,p90_tpot,p95_tpot,p99_tpot,mean_itl,p90_itl,p95_itl,p99_itl,mean_e2el,p90_e2el,p95_e2el,p99_e2el"
        write_csv_header "$SLA_RESULTS_CSV" "Scenario ID,Scenario Name,Repeat Rate,Input Length,Output Length,Tested Concurrencies,Turning Point Concurrency,Result State,Stop Reason,Mean TTFT (ms),Mean TPOT (ms),Mean E2EL (ms),TTFT SLA Status,TPOT SLA Status,Overall SLA Status,Num Prompts,Result Directory"
    else
        write_csv_header "$CORE_METRICS_CSV" "scenario_name,input_length,output_length,request_rate,max_concurrency,num_prompts,total_input_len,prefix_ratio,output_start,duration,failed_requests,request_throughput,output_token_throughput,total_token_throughput,mean_ttft,p90_ttft,p95_ttft,p99_ttft,mean_tpot,p90_tpot,p95_tpot,p99_tpot,mean_itl,p90_itl,p95_itl,p99_itl,mean_e2el,p90_e2el,p95_e2el,p99_e2el"
    fi
    success_count=0
}

read_combo_metrics() {
    local combo_dir="$1"
    local json_file=""
    local candidate

    LAST_TOTAL_INPUT_TOKENS=""
    LAST_TOTAL_OUTPUT_TOKENS=""
    LAST_DURATION=""
    LAST_REQUEST_THROUGHPUT=""
    LAST_OUTPUT_THROUGHPUT=""
    LAST_TOTAL_TOKEN_THROUGHPUT=""
    LAST_MEAN_TTFT_MS=""
    LAST_P90_TTFT_MS=""
    LAST_P95_TTFT_MS=""
    LAST_P99_TTFT_MS=""
    LAST_MEAN_TPOT_MS=""
    LAST_P90_TPOT_MS=""
    LAST_P95_TPOT_MS=""
    LAST_P99_TPOT_MS=""
    LAST_MEAN_ITL_MS=""
    LAST_P90_ITL_MS=""
    LAST_P95_ITL_MS=""
    LAST_P99_ITL_MS=""
    LAST_MEAN_E2EL_MS=""
    LAST_P90_E2EL_MS=""
    LAST_P95_E2EL_MS=""
    LAST_P99_E2EL_MS=""
    LAST_COMPLETED_REQUESTS=""
    LAST_FAILED_REQUESTS=""
    LAST_TTFT_SLA_STATUS=""
    LAST_TPOT_SLA_STATUS=""
    LAST_OVERALL_SLA_STATUS=""
    LAST_STATE=""

    for candidate in "$combo_dir"/*.json; do
        if [[ -f "$candidate" ]]; then
            json_file="$candidate"
            break
        fi
    done

    if [[ -z "$json_file" ]]; then
        return 1
    fi

    LAST_TOTAL_INPUT_TOKENS=$(clean_number "$(extract_json_value "$json_file" "total_input_tokens")")
    LAST_TOTAL_OUTPUT_TOKENS=$(clean_number "$(extract_json_value "$json_file" "total_output_tokens")")
    LAST_DURATION=$(clean_number "$(extract_json_value "$json_file" "duration")")
    LAST_REQUEST_THROUGHPUT=$(clean_number "$(extract_json_value "$json_file" "request_throughput")")
    LAST_OUTPUT_THROUGHPUT=$(clean_number "$(extract_json_value "$json_file" "output_throughput")")
    LAST_TOTAL_TOKEN_THROUGHPUT=$(clean_number "$(extract_json_value "$json_file" "total_token_throughput")")
    LAST_MEAN_TTFT_MS=$(clean_number "$(extract_json_value "$json_file" "mean_ttft_ms")")
    LAST_P90_TTFT_MS=$(clean_number "$(extract_json_value "$json_file" "p90_ttft_ms")")
    LAST_P95_TTFT_MS=$(clean_number "$(extract_json_value "$json_file" "p95_ttft_ms")")
    LAST_P99_TTFT_MS=$(clean_number "$(extract_json_value "$json_file" "p99_ttft_ms")")
    LAST_MEAN_TPOT_MS=$(clean_number "$(extract_json_value "$json_file" "mean_tpot_ms")")
    LAST_P90_TPOT_MS=$(clean_number "$(extract_json_value "$json_file" "p90_tpot_ms")")
    LAST_P95_TPOT_MS=$(clean_number "$(extract_json_value "$json_file" "p95_tpot_ms")")
    LAST_P99_TPOT_MS=$(clean_number "$(extract_json_value "$json_file" "p99_tpot_ms")")
    LAST_MEAN_ITL_MS=$(clean_number "$(extract_json_value "$json_file" "mean_itl_ms")")
    LAST_P90_ITL_MS=$(clean_number "$(extract_json_value "$json_file" "p90_itl_ms")")
    LAST_P95_ITL_MS=$(clean_number "$(extract_json_value "$json_file" "p95_itl_ms")")
    LAST_P99_ITL_MS=$(clean_number "$(extract_json_value "$json_file" "p99_itl_ms")")
    LAST_MEAN_E2EL_MS=$(clean_number "$(extract_json_value "$json_file" "mean_e2el_ms")")
    LAST_P90_E2EL_MS=$(clean_number "$(extract_json_value "$json_file" "p90_e2el_ms")")
    LAST_P95_E2EL_MS=$(clean_number "$(extract_json_value "$json_file" "p95_e2el_ms")")
    LAST_P99_E2EL_MS=$(clean_number "$(extract_json_value "$json_file" "p99_e2el_ms")")
    LAST_COMPLETED_REQUESTS=$(clean_number "$(extract_json_value "$json_file" "completed")")
    LAST_FAILED_REQUESTS=$(clean_number "$(extract_json_value "$json_file" "failed")")

    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        if (( LAST_FAILED_REQUESTS > 0 || LAST_COMPLETED_REQUESTS == 0 )); then
            LAST_TTFT_SLA_STATUS="REQUEST_FAILURE"
            LAST_TPOT_SLA_STATUS="REQUEST_FAILURE"
            LAST_OVERALL_SLA_STATUS="REQUEST_FAILURE"
            LAST_STATE="REQUEST_FAILURE"
        else
            LAST_TTFT_SLA_STATUS=$(compare_metric_to_sla "$LAST_MEAN_TTFT_MS" "$CURRENT_SLA_TTFT_TARGET_MS")
            LAST_TPOT_SLA_STATUS=$(compare_metric_to_sla "$LAST_MEAN_TPOT_MS" "$CURRENT_SLA_TPOT_TARGET_MS")
            LAST_OVERALL_SLA_STATUS=$(combine_sla_metric_status "$LAST_TTFT_SLA_STATUS" "$LAST_TPOT_SLA_STATUS")
            LAST_STATE=$(classify_sla_state "$LAST_MEAN_TTFT_MS" "$LAST_MEAN_TPOT_MS")
        fi
    else
        LAST_TTFT_SLA_STATUS=$(compare_metric_to_sla "$LAST_MEAN_TTFT_MS" "$SLA_TTFT_TARGET_MS")
        LAST_TPOT_SLA_STATUS=$(compare_metric_to_sla "$LAST_MEAN_TPOT_MS" "$SLA_TPOT_TARGET_MS")
        LAST_OVERALL_SLA_STATUS=$(combine_sla_metric_status "$LAST_TTFT_SLA_STATUS" "$LAST_TPOT_SLA_STATUS")
    fi

    return 0
}

append_core_metrics_row() {
    local scenario_id="$1"
    local scenario_name="$2"
    local repeat_rate="$3"
    local num_prompts="$4"
    local input_len="$5"
    local output_len="$6"
    local max_concurrency="$7"
    local request_rate
    local resolved_scenario_name
    local prefix_ratio
    local output_start

    request_rate=$(resolve_request_rate)
    resolved_scenario_name="${scenario_name:-standard}"
    prefix_ratio=$(resolve_prefix_ratio "$input_len" "$repeat_rate")
    output_start=$(resolve_output_start "$output_len")

    append_sorted_core_metrics_row "$resolved_scenario_name,$input_len,$output_len,$request_rate,$max_concurrency,$num_prompts,$input_len,$prefix_ratio,$output_start,$LAST_DURATION,$LAST_FAILED_REQUESTS,$LAST_REQUEST_THROUGHPUT,$LAST_OUTPUT_THROUGHPUT,$LAST_TOTAL_TOKEN_THROUGHPUT,$LAST_MEAN_TTFT_MS,$LAST_P90_TTFT_MS,$LAST_P95_TTFT_MS,$LAST_P99_TTFT_MS,$LAST_MEAN_TPOT_MS,$LAST_P90_TPOT_MS,$LAST_P95_TPOT_MS,$LAST_P99_TPOT_MS,$LAST_MEAN_ITL_MS,$LAST_P90_ITL_MS,$LAST_P95_ITL_MS,$LAST_P99_ITL_MS,$LAST_MEAN_E2EL_MS,$LAST_P90_E2EL_MS,$LAST_P95_E2EL_MS,$LAST_P99_E2EL_MS"
    success_count=$((success_count + 1))
}

compose_random_dataset_args() {
    local input_len="$1"
    local output_len="$2"
    local prefix_rate="${3:-}"
    local range_ratio="${4:-}"
    local random_prefix_len=0
    local random_context_len="$input_len"

    if [[ -n "$prefix_rate" ]] && awk -v rate="$prefix_rate" 'BEGIN { exit !(rate > 0) }'; then
        random_prefix_len=$(awk -v input_len="$input_len" -v rate="$prefix_rate" 'BEGIN {
            prefix = int(input_len * rate + 0.5)
            if (prefix >= input_len) {
                prefix = input_len - 1
            }
            if (prefix < 0) {
                prefix = 0
            }
            print prefix
        }')
        random_context_len=$((input_len - random_prefix_len))
    fi

    RANDOM_DATASET_ARGS=(--random-input-len "$random_context_len" --random-output-len "$output_len")
    if [[ -n "$range_ratio" ]]; then
        RANDOM_DATASET_ARGS+=(--random-range-ratio "$range_ratio")
    fi
    if (( random_prefix_len > 0 )); then
        RANDOM_DATASET_ARGS+=(--random-prefix-len "$random_prefix_len")
    fi
}

strip_random_dataset_flags() {
    local -a filtered_args=()
    local skip_next=false
    local arg

    for arg in "${dataset_args_arr[@]}"; do
        if [[ "$skip_next" == true ]]; then
            skip_next=false
            continue
        fi
        case "$arg" in
            --random-input-len|--random-output-len|--random-prefix-len|--prefix-rate|--prefix_rate)
                skip_next=true
                ;;
            --random-input-len=*|--random-output-len=*|--random-prefix-len=*|--prefix-rate=*|--prefix_rate=*)
                ;;
            *)
                filtered_args+=("$arg")
                ;;
        esac
    done

    dataset_args_arr=("${filtered_args[@]}")
}

build_dataset_args() {
    local input_len="$1"
    local output_len="$2"
    local repeat_rate="${3:-}"
    local dataset_name
    local current_dataset_name
    local prefix_rate=""
    local dataset_path=""
    local dataset_subset=""

    dataset_name=$(resolve_default_dataset_name)

    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        if [[ "$dataset_name" == "speed_bench" ]]; then
            dataset_path=$(extract_dataset_path_from_args)
            dataset_args_arr=(--dataset-name speed_bench)

            if [[ -n "$dataset_path" ]]; then
                if (( input_len <= 1024 )); then
                    dataset_subset="$dataset_path/throughput_1k"
                elif (( input_len <= 2048 )); then
                    dataset_subset="$dataset_path/throughput_2k"
                elif (( input_len <= 8192 )); then
                    dataset_subset="$dataset_path/throughput_8k"
                elif (( input_len <= 16384 )); then
                    dataset_subset="$dataset_path/throughput_16k"
                elif (( input_len <= 32768 )); then
                    dataset_subset="$dataset_path/throughput_32k"
                else
                    dataset_subset="$dataset_path/qualitative"
                fi
                dataset_args_arr+=(--input-len "$input_len" --speed-bench-output-len "$output_len" --speed-bench-dataset-subset "$dataset_subset")
            else
                dataset_args_arr+=(--input-len "$input_len" --speed-bench-output-len "$output_len")
            fi

            return 0
        fi

        prefix_rate="${repeat_rate:-${CURRENT_REPEAT_RATE:-0.0}}"
        compose_random_dataset_args "$input_len" "$output_len" "$prefix_rate" "0.0"
        dataset_args_arr=(--dataset-name random "${RANDOM_DATASET_ARGS[@]}")

        return 0
    fi

    # 非 SLA 模式：前缀重复率优先级 组合第5字段 > --prefix-rate > --dataset-args 中的 --prefix-rate
    if [[ -n "$repeat_rate" ]]; then
        prefix_rate="$repeat_rate"
    elif [[ -n "${PREFIX_RATE_ARG:-}" ]]; then
        prefix_rate="$PREFIX_RATE_ARG"
    fi

    if [[ -n "${DATASET_ARGS:-}" ]]; then
        eval "dataset_args_arr=(${DATASET_ARGS})"
        current_dataset_name="$dataset_name"
        if [[ "$DATASET_ARGS" =~ --dataset-name[[:space:]=]+([^[:space:]]+) ]]; then
            current_dataset_name="${BASH_REMATCH[1]}"
            current_dataset_name="${current_dataset_name%\"}"
            current_dataset_name="${current_dataset_name#\"}"
            current_dataset_name="${current_dataset_name%\'}"
            current_dataset_name="${current_dataset_name#\'}"
        fi

        if [[ -z "$prefix_rate" && "$DATASET_ARGS" =~ --prefix[-_]rate[[:space:]=]+([0-9.]+) ]]; then
            prefix_rate="${BASH_REMATCH[1]}"
        fi

        strip_random_dataset_flags

        if [[ "$current_dataset_name" == "sonnet" ]]; then
            dataset_args_arr+=(--sonnet-input-len "$input_len" --sonnet-output-len "$output_len")
        elif [[ "$current_dataset_name" == "sharegpt" ]]; then
            dataset_args_arr+=(--input-len "$input_len" --sharegpt-output-len "$output_len")
        elif [[ "$current_dataset_name" == "burstgpt" ]]; then
            dataset_args_arr+=(--burstgpt-input-len "$input_len" --burstgpt-output-len "$output_len")
        elif [[ "$current_dataset_name" == "prefix_repetition" ]]; then
            if [[ -n "$prefix_rate" ]]; then
                prefix_len=$(awk "BEGIN {printf \"%.0f\", $input_len * $prefix_rate}")
                suffix_len=$(awk "BEGIN {printf \"%.0f\", $input_len - $input_len * $prefix_rate}")
                dataset_args_arr+=(--prefix-repetition-prefix-len "$prefix_len" --prefix-repetition-suffix-len "$suffix_len" --prefix-repetition-output-len "$output_len")
            else
                dataset_args_arr=(
                    --dataset-name "$dataset_name"
                    --random-input-len "$input_len"
                    --random-output-len "$output_len"
                )
            fi
        elif [[ "$current_dataset_name" == "random" || "$current_dataset_name" == "random--mm" ]]; then
            compose_random_dataset_args "$input_len" "$output_len" "$prefix_rate" ""
            dataset_args_arr+=("${RANDOM_DATASET_ARGS[@]}")
        elif [[ "$current_dataset_name" == "speed_bench" ]]; then
            dataset_path=""
            if [[ "$DATASET_ARGS" =~ --dataset-path[[:space:]=]+([^[:space:]]+) ]]; then
                dataset_path="${BASH_REMATCH[1]}"
                dataset_path="${dataset_path%\"}"
                dataset_path="${dataset_path#\"}"
                dataset_path="${dataset_path%\'}"
                dataset_path="${dataset_path#\'}"
            fi

            if [[ -n "$dataset_path" ]]; then
                if (( input_len <= 1024 )); then
                    dataset_subset="$dataset_path/throughput_1k"
                elif (( input_len <= 2048 )); then
                    dataset_subset="$dataset_path/throughput_2k"
                elif (( input_len <= 8192 )); then
                    dataset_subset="$dataset_path/throughput_8k"
                elif (( input_len <= 16384 )); then
                    dataset_subset="$dataset_path/throughput_16k"
                elif (( input_len <= 32768 )); then
                    dataset_subset="$dataset_path/throughput_32k"
                else
                    dataset_subset="$dataset_path/qualitative"
                fi
                dataset_args_arr+=(--input-len "$input_len" --speed-bench-output-len "$output_len" --speed-bench-dataset-subset "$dataset_subset")
            else
                dataset_args_arr+=(--input-len "$input_len" --speed-bench-output-len "$output_len")
            fi
        fi
    else
        compose_random_dataset_args "$input_len" "$output_len" "$prefix_rate" ""
        dataset_args_arr=(
            --dataset-name "$dataset_name"
            "${RANDOM_DATASET_ARGS[@]}"
        )
    fi
}

# 调用服务端 /reset_prefix_cache 清空 prefix cache，失败时仅记录日志并返回非 0
reset_server_prefix_cache() {
    local benchmark_base_url="$1"
    local response

    if ! command -v curl >/dev/null 2>&1; then
        log "Prefix Cache 清理失败: 未找到 curl 命令"
        return 1
    fi

    if ! response=$(curl -fsS -m 30 -X POST "${benchmark_base_url}/reset_prefix_cache"); then
        log "Prefix Cache 清理请求失败: ${benchmark_base_url}/reset_prefix_cache"
        return 1
    fi

    if ! grep -Eq '"success"[[:space:]]*:[[:space:]]*true' <<< "$response"; then
        log "Prefix Cache 清理未成功: $response"
        return 1
    fi

    log "Prefix Cache 清理成功: ${benchmark_base_url}/reset_prefix_cache"
    return 0
}

# 判断当前 SLA 场景是否在 prefix cache 清空白名单内
is_prefix_cache_reset_scenario() {
    local scenario_name="$1"
    local s
    [[ -z "$scenario_name" ]] && return 1
    [[ ${#PREFIX_CACHE_RESET_SCENARIOS[@]} -eq 0 ]] && return 1
    for s in "${PREFIX_CACHE_RESET_SCENARIOS[@]}"; do
        [[ "$scenario_name" == "$s" ]] && return 0
    done
    return 1
}

run_single_combo() {
    local input_len="$1"
    local output_len="$2"
    local num_prompts="$3"
    local max_concurrency="$4"
    local scenario_id="${5:-}"
    local scenario_name="${6:-}"
    local repeat_rate="${7:-}"
    local combo_dir_name
    local benchmark_base_url
    local benchmark_args

    if [[ -n "$scenario_id" ]]; then
        combo_dir_name=$(get_sla_combo_dir_name "$scenario_id" "$input_len" "$output_len" "$num_prompts" "$max_concurrency")
    else
        combo_dir_name=$(get_combo_dir_name "$input_len" "$output_len" "$num_prompts" "$max_concurrency" "$repeat_rate")
    fi

    COMBO_DIR="${RESULTS_DIR}/${combo_dir_name}"
    mkdir -p "$COMBO_DIR"
    EXEC_LOG="${COMBO_DIR}/execution.log"
    START_TIME=$(date +%s)

    if [[ -n "$BASE_URL" ]]; then
        benchmark_base_url=$(echo "$BASE_URL" | sed -E 's|/v1/?$||; s|/$||')
    else
        benchmark_base_url="http://${TEST_IP}:${PORT}"
    fi

    build_dataset_args "$input_len" "$output_len" "$repeat_rate"

    benchmark_args=(
        --backend openai-chat
        --base-url "$benchmark_base_url"
        --endpoint '/v1/chat/completions'
        --model "$MODEL_NAME"
        --tokenizer "$TOKENIZER_PATH"
        --trust-remote-code
        --temperature "$TEMPERATURE"
        --percentile-metrics 'ttft,tpot,itl,e2el'
        --metric-percentiles '90,95,99'
        "${dataset_args_arr[@]}"
        --ignore-eos
        --num-warmups "$WARMUPS_NUM"
        --num-prompts "$num_prompts"
        --max-concurrency "$max_concurrency"
        --save-result
        --result-dir "$COMBO_DIR"
    )

    if [[ -n "$REQUEST_RATE" ]]; then
        benchmark_args+=(--request-rate "$REQUEST_RATE")
    fi
    if [[ -n "$API_KEY" ]]; then
        benchmark_args+=(--header "Authorization=Bearer $API_KEY")
    fi

    log "Testing: input=${input_len}, output=${output_len}, prompts=${num_prompts}, concurrency=${max_concurrency}, temp=${TEMPERATURE}$(if [[ -n "$REQUEST_RATE" ]]; then echo ", request_rate=${REQUEST_RATE}"; else echo ", request_rate=unlimited"; fi)${repeat_rate:+, prefix_rate=${repeat_rate}}${scenario_name:+, scenario=${scenario_name}}" > "$EXEC_LOG"
    # prefix cache 清空：SLA 模式按场景白名单，标准模式每个组合前均清空（均受 --no-reset-prefix-cache 控制）
    if [[ "$PREFIX_CACHE_RESET" == true ]]; then
        if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
            if is_prefix_cache_reset_scenario "${scenario_name:-}"; then
                if ! reset_server_prefix_cache "$benchmark_base_url" >> "$EXEC_LOG" 2>&1; then
                    log "Prefix Cache 清理失败，继续执行当前探测点测试" >> "$EXEC_LOG"
                fi
            else
                log "场景(${scenario_name:-N/A})不在 prefix cache 清空白名单，跳过 reset" >> "$EXEC_LOG"
            fi
        elif ! reset_server_prefix_cache "$benchmark_base_url" >> "$EXEC_LOG" 2>&1; then
            log "Prefix Cache 清理失败，继续执行当前组合测试" >> "$EXEC_LOG"
        fi
    fi
    log "开始测试组合: input=${input_len}, output=${output_len}, prompts=${num_prompts}, concurrency=${max_concurrency}${repeat_rate:+, prefix_rate=${repeat_rate}}${scenario_name:+, scenario=${scenario_name}} ..."
    set +e

    log "执行命令: vllm  bench serve ${benchmark_args[*]}" >> "$EXEC_LOG"
    vllm  bench serve "${benchmark_args[@]}" >> "$EXEC_LOG" 2>&1

    EXIT_STATUS=$?
    set -e
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    DURATION_STR=$(printf "%02d:%02d:%02d" $((DURATION/3600)) $((((DURATION%3600)/60))) $((DURATION%60)))

    if [[ $EXIT_STATUS -eq 0 ]]; then
        if ! read_combo_metrics "$COMBO_DIR"; then
            EXIT_STATUS=1
            echo "Error: no result json found in $COMBO_DIR" >> "$EXEC_LOG"
        fi
    fi

    if [[ $EXIT_STATUS -eq 0 ]]; then
        STATUS="SUCCESS"
        STATUS_COLOR="\033[32m"
        append_core_metrics_row "$scenario_id" "$scenario_name" "$repeat_rate" "$num_prompts" "$input_len" "$output_len" "$max_concurrency"
        log "完成测试组合: input=${input_len}, output=${output_len}, prompts=${num_prompts}, concurrency=${max_concurrency} [SUCCESS - ${DURATION_STR}]"
    else
        STATUS="FAILED"
        STATUS_COLOR="\033[31m"
        log "完成测试组合: input=${input_len}, output=${output_len}, prompts=${num_prompts}, concurrency=${max_concurrency} [FAILED - ${DURATION_STR}]"
    fi

    printf "%-10s | %-5s | %-5s | %-5s | %-5s | ${STATUS_COLOR}%-7s\033[0m | %-9s | %s\n" \
        "$(date +%T)" "$input_len" "$output_len" "$num_prompts" "$max_concurrency" "$STATUS" "$DURATION_STR" "$COMBO_DIR" \
        >> "${RESULTS_DIR}/summary.log"

    LAST_COMBO_DIR="$COMBO_DIR"
    LAST_NUM_PROMPTS="$num_prompts"

    return "$EXIT_STATUS"
}

reset_sla_tracking() {
    declare -gA SCENARIO_STATE_MAP=()
    declare -gA SCENARIO_TTFT_MAP=()
    declare -gA SCENARIO_TPOT_MAP=()
    declare -gA SCENARIO_E2EL_MAP=()
    declare -gA SCENARIO_TTFT_SLA_STATUS_MAP=()
    declare -gA SCENARIO_TPOT_SLA_STATUS_MAP=()
    declare -gA SCENARIO_OVERALL_SLA_STATUS_MAP=()
    declare -gA SCENARIO_PROMPTS_MAP=()
    declare -gA SCENARIO_COMBO_DIR_MAP=()
    declare -ga SCENARIO_TESTED_CONCURRENCIES=()
}

run_sla_probe() {
    local concurrency="$1"
    local num_prompts

    if [[ -n "${SCENARIO_STATE_MAP[$concurrency]+x}" ]]; then
        return 0
    fi

    num_prompts=$(calculate_num_prompts "$CURRENT_INPUT_LEN" "$CURRENT_OUTPUT_LEN" "$concurrency")
    if ! run_single_combo "$CURRENT_INPUT_LEN" "$CURRENT_OUTPUT_LEN" "$num_prompts" "$concurrency" "$CURRENT_SCENARIO_ID" "$CURRENT_SCENARIO_NAME" "$CURRENT_REPEAT_RATE"; then
        return 1
    fi

    SCENARIO_STATE_MAP["$concurrency"]="$LAST_STATE"
    SCENARIO_TTFT_MAP["$concurrency"]="$LAST_MEAN_TTFT_MS"
    SCENARIO_TPOT_MAP["$concurrency"]="$LAST_MEAN_TPOT_MS"
    SCENARIO_E2EL_MAP["$concurrency"]="$LAST_MEAN_E2EL_MS"
    SCENARIO_TTFT_SLA_STATUS_MAP["$concurrency"]="$LAST_TTFT_SLA_STATUS"
    SCENARIO_TPOT_SLA_STATUS_MAP["$concurrency"]="$LAST_TPOT_SLA_STATUS"
    SCENARIO_OVERALL_SLA_STATUS_MAP["$concurrency"]="$LAST_OVERALL_SLA_STATUS"
    SCENARIO_PROMPTS_MAP["$concurrency"]="$num_prompts"
    SCENARIO_COMBO_DIR_MAP["$concurrency"]="$LAST_COMBO_DIR"
    SCENARIO_TESTED_CONCURRENCIES+=("$concurrency")
    return 0
}

append_sla_result_row() {
    local final_concurrency="$1"
    local final_state="$2"
    local final_stop_reason="$3"
    local tested_concurrencies="$4"
    local final_ttft="$5"
    local final_tpot="$6"
    local final_e2el="$7"
    local final_ttft_sla_status="$8"
    local final_tpot_sla_status="$9"
    local final_overall_sla_status="${10}"
    local final_num_prompts="${11}"
    local final_combo_dir="${12}"

    echo "$CURRENT_SCENARIO_ID,$CURRENT_SCENARIO_NAME,$CURRENT_REPEAT_RATE,$CURRENT_INPUT_LEN,$CURRENT_OUTPUT_LEN,$tested_concurrencies,$final_concurrency,$final_state,$final_stop_reason,$final_ttft,$final_tpot,$final_e2el,$final_ttft_sla_status,$final_tpot_sla_status,$final_overall_sla_status,$final_num_prompts,$final_combo_dir" >> "$SLA_RESULTS_CSV"
}

run_standard_mode() {
    local input_len output_len num_prompts max_concurrency repeat_rate
    TEST_FAILED=0
    for combo in "${combinations[@]}"; do
        read input_len output_len num_prompts max_concurrency repeat_rate <<< "$combo"
        repeat_rate="${repeat_rate:-}"
        if ! run_single_combo "$input_len" "$output_len" "$num_prompts" "$max_concurrency" "" "" "$repeat_rate"; then
            echo ""
            log "测试组合失败 (input=${input_len}, output=${output_len}, prompts=${num_prompts}, concurrency=${max_concurrency}${repeat_rate:+, prefix_rate=${repeat_rate}})"
            log "根据配置，提前结束后续所有测试..."
            TEST_FAILED=1
            break
        fi
    done
}

run_sla_turning_point_mode() {
    local scenario
    local scenario_index=0
    local lower_bound
    local upper_bound
    local found_turning_point
    local probe_concurrency
    local midpoint
    local tested_list
    local final_concurrency
    local final_state
    local final_stop_reason
    local final_ttft
    local final_tpot
    local final_e2el
    local final_ttft_sla_status
    local final_tpot_sla_status
    local final_overall_sla_status
    local final_num_prompts
    local final_combo_dir

    TEST_FAILED=0
    for scenario in "${SLA_SCENARIOS[@]}"; do
        scenario_index=$((scenario_index + 1))
        IFS='|' read -r CURRENT_INPUT_LEN CURRENT_OUTPUT_LEN CURRENT_SCENARIO_NAME CURRENT_REPEAT_RATE <<< "$scenario"
        printf -v CURRENT_SCENARIO_ID "scenario%02d" "$scenario_index"
        set_current_sla_thresholds "$CURRENT_INPUT_LEN" "$CURRENT_OUTPUT_LEN" "$CURRENT_SCENARIO_NAME" "$CURRENT_REPEAT_RATE"

        reset_sla_tracking
        log "开始搜索 SLA 拐点: ${CURRENT_SCENARIO_ID}, scenario=${CURRENT_SCENARIO_NAME}, input=${CURRENT_INPUT_LEN}, output=${CURRENT_OUTPUT_LEN}, repeat=${CURRENT_REPEAT_RATE}, ttft=${CURRENT_SLA_TTFT_KNEE_MS}-${CURRENT_SLA_TTFT_BREAK_MS}ms, tpot=${CURRENT_SLA_TPOT_KNEE_MS}-${CURRENT_SLA_TPOT_BREAK_MS}ms"

        for probe_concurrency in 1 4 8; do
            if ! run_sla_probe "$probe_concurrency"; then
                TEST_FAILED=1
                return 1
            fi
        done

        lower_bound=""
        upper_bound=""
        found_turning_point=0

        if [[ "${SCENARIO_STATE_MAP[1]}" != "SAFE" ]]; then
            lower_bound=0
            upper_bound=1
            found_turning_point=1
        elif [[ "${SCENARIO_STATE_MAP[4]}" != "SAFE" ]]; then
            lower_bound=1
            upper_bound=4
            found_turning_point=1
        elif [[ "${SCENARIO_STATE_MAP[8]}" != "SAFE" ]]; then
            lower_bound=4
            upper_bound=8
            found_turning_point=1
        else
            lower_bound=8
            for probe_concurrency in "${SLA_EXPANSION_CONCURRENCIES[@]}"; do
                if ! run_sla_probe "$probe_concurrency"; then
                    TEST_FAILED=1
                    return 1
                fi
                if [[ "${SCENARIO_STATE_MAP[$probe_concurrency]}" != "SAFE" ]]; then
                    upper_bound="$probe_concurrency"
                    found_turning_point=1
                    break
                fi
                lower_bound="$probe_concurrency"
            done
        fi

        if [[ "$found_turning_point" -eq 1 && "$upper_bound" -gt 1 ]]; then
            while (( upper_bound - lower_bound > 1 )); do
                midpoint=$(((lower_bound + upper_bound) / 2))
                if ! run_sla_probe "$midpoint"; then
                    TEST_FAILED=1
                    return 1
                fi

                if [[ "${SCENARIO_STATE_MAP[$midpoint]}" == "SAFE" ]]; then
                    lower_bound="$midpoint"
                else
                    upper_bound="$midpoint"
                fi
            done
        fi

        if [[ "$found_turning_point" -eq 1 ]]; then
            final_concurrency="$upper_bound"
            final_state="${SCENARIO_STATE_MAP[$final_concurrency]}"
            final_stop_reason="NEAREST_${final_state}"
            final_ttft="${SCENARIO_TTFT_MAP[$final_concurrency]}"
            final_tpot="${SCENARIO_TPOT_MAP[$final_concurrency]}"
            final_e2el="${SCENARIO_E2EL_MAP[$final_concurrency]}"
            final_ttft_sla_status="${SCENARIO_TTFT_SLA_STATUS_MAP[$final_concurrency]}"
            final_tpot_sla_status="${SCENARIO_TPOT_SLA_STATUS_MAP[$final_concurrency]}"
            final_overall_sla_status="${SCENARIO_OVERALL_SLA_STATUS_MAP[$final_concurrency]}"
            final_num_prompts="${SCENARIO_PROMPTS_MAP[$final_concurrency]}"
            final_combo_dir="${SCENARIO_COMBO_DIR_MAP[$final_concurrency]}"
        else
            final_concurrency="N/A"
            final_state="SAFE"
            final_stop_reason="NOT_FOUND_UP_TO_MAX_CONCURRENCY"
            final_ttft="N/A"
            final_tpot="N/A"
            final_e2el="N/A"
            final_ttft_sla_status="NOT_REACHED"
            final_tpot_sla_status="NOT_REACHED"
            final_overall_sla_status="NOT_REACHED"
            final_num_prompts="N/A"
            final_combo_dir="N/A"
        fi

        tested_list=$(printf "%s;" "${SCENARIO_TESTED_CONCURRENCIES[@]}")
        tested_list="${tested_list%;}"
        append_sla_result_row "$final_concurrency" "$final_state" "$final_stop_reason" "$tested_list" "$final_ttft" "$final_tpot" "$final_e2el" "$final_ttft_sla_status" "$final_tpot_sla_status" "$final_overall_sla_status" "$final_num_prompts" "$final_combo_dir"
        if [[ "$found_turning_point" -eq 1 ]]; then
            log "完成 SLA 拐点搜索: ${CURRENT_SCENARIO_ID}, scenario=${CURRENT_SCENARIO_NAME}, nearest_turning_point=${final_concurrency}, state=${final_state}, stop_reason=${final_stop_reason}; 停止本组并进入下一组"
        else
            log "完成 SLA 拐点搜索: ${CURRENT_SCENARIO_ID}, scenario=${CURRENT_SCENARIO_NAME}, stop_reason=${final_stop_reason}"
        fi
    done
}

show_help() {
    cat << 'EOF'
 ===========================================================================
        AI Model Benchmark Testing Script
 ===========================================================================

USAGE:
  ./benchmark.sh --model-path MODEL_PATH --port PORT [OPTIONS]
  ./benchmark.sh --model-path MODEL_PATH --base-url URL [OPTIONS]

MODE 1 - IP:Port:
  --model-path PATH     Path to model directory (e.g. /data/models/Qwen/Qwen3-32B)
  --port NUMBER         API server port (e.g. 4567)
  --ip ADDRESS          API server IP (default: 127.0.0.1)

MODE 2 - Base URL:
  --model-path PATH     Path to model directory (e.g. /home/models/Meta-Llama-3-8B)
  --base-url URL        Full API base URL (e.g. http://192.0.2.150:10092/v1/)
  --api-key KEY         API key for authentication (optional)

COMMON OPTIONS:
  --temperature FLOAT   Inference temperature (default: 0.65)
  --request-rate NUM   Request rate per second (optional, if not specified, no rate limit)
    --accelerator-type TYPE  Accelerator type for SLA thresholds: nvidia or ascend (optional, auto-detect by default)
    --enable-speculative    Use speed_bench dataset selection for speculative inference
    --no-reset-prefix-cache    Disable resetting server prefix cache before each vllm bench serve (default: enabled)
    --sla-reset-scenarios STR  Comma-separated scenario names that reset prefix cache before probing (default: 对话,通用复杂任务,合同分析)
  --input-len NUM       Input length for single test (e.g., 128)
  --output-len NUM      Output length for single test (e.g., 128)
  --num-prompts NUM     Number of prompts for single test (e.g., 1)
  --max-concurrency NUM Max concurrency for single test (e.g., 1)
  --prefix-rate FLOAT   Prefix repetition ratio for random dataset (0~1, e.g., 0.6)
    -c, --combinations STR  Custom combinations ("input output prompts concurrency [prefix_rate]")
                            prefix_rate is optional; default dataset is random
    -r, --result-dir DIR    Result directory (optional)
    -M, --mode MODE         Test mode (optional, supports: sla-turning-point)

EXAMPLES:
  ./benchmark.sh --model-path /data/models/Qwen/Qwen3-32B --port 4567 --input-len 128 --output-len 128 --num-prompts 1 --max-concurrency 1
  ./benchmark.sh --model-path /data/models/Qwen/Qwen3-32B --port 4567 -c "128 128 1 1" -c "256 256 1 1"
  ./benchmark.sh --model-path /data/models/Qwen/Qwen3-32B --port 4567 -c "65536 1024 40 2 0.9"
  ./benchmark.sh --model-path /data/models/Qwen/Qwen3-32B --port 4567 --prefix-rate 0.6 -c "8192 1024 150 30"
    ./benchmark.sh --model-path /data/models/Qwen/Qwen3-32B --base-url http://127.0.0.1:8000/v1 -M sla-turning-point

 ===========================================================================
EOF
    exit 0
}

BASE_URL=""
API_KEY=""
MODE=""
DATASET_ARGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ip)
            TEST_IP="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --base-url|--base_url)
            BASE_URL="$2"
            shift 2
            ;;
        --api-key|--api_key)
            API_KEY="$2"
            shift 2
            ;;
        --model-path|--model-path)
            TOKENIZER_PATH="$2"
            #MODEL_NAME=$(basename "$2")
            shift 2
            ;;
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --temperature)
            TEMPERATURE="$2"
            shift 2
            ;;
        --enable-speculative|--enable-speculative-inference|--speculative-inference|--speculative-decoding)
            SPECULATIVE_INFERENCE_ENABLED=true
            shift
            ;;
        --accelerator-type|--accelerator_type|--device-type|--device_type)
            ACCELERATOR_TYPE=$(echo "$2" | tr '[:upper:]' '[:lower:]')
            if [[ "$ACCELERATOR_TYPE" != "nvidia" && "$ACCELERATOR_TYPE" != "ascend" ]]; then
                echo "Error: --accelerator-type must be either nvidia or ascend"
                exit 1
            fi
            shift 2
            ;;
        --input-len)
            INPUT_LEN_ARG="$2"
            shift 2
            ;;
        --output-len)
            OUTPUT_LEN_ARG="$2"
            shift 2
            ;;
        --num-prompts)
            NUM_PROMPTS_ARG="$2"
            shift 2
            ;;
        --max-concurrency)
            MAX_CONCURRENCY_ARG="$2"
            shift 2
            ;;
        --prefix-rate|--prefix_rate|--prefix-repetition-rate|--prefix-repetition-ratio)
            PREFIX_RATE_ARG="$2"
            shift 2
            ;;
        --request-rate)
            REQUEST_RATE="$2"
            if [[ "$REQUEST_RATE" == "0" ]]; then
                REQUEST_RATE=""
            fi
            shift 2
            ;;
        --no-reset-prefix-cache)
            PREFIX_CACHE_RESET=false
            shift
            ;;
        --sla-reset-scenarios)
            SLA_RESET_PREFIX_SCENARIOS_STR="$2"
            shift 2
            ;;
         -r|--result-dir)
            RESULTS_DIR="$2"
            shift 2
            ;; 
        -M|--mode)
            MODE="$2"
            shift 2
            ;;
        --dataset-args)
            DATASET_ARGS="$2"
            shift 2
            ;;
        -c|--combinations)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                IFS=',' read -r -a custom_combos <<< "$1"
                for combo in "${custom_combos[@]}"; do
                    # Trim leading/trailing whitespace
                    combo=$(echo "$combo" | xargs)
                    if [[ -n "$combo" ]]; then
                        CUSTOM_COMBINATIONS+=("$combo")
                    fi
                done
                shift
            done
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo "Unknown parameter: $1"
            show_help
            exit 1
            ;;
    esac
done

# 将 prefix cache 清空白名单字符串解析为数组（供 SLA 模式场景级过滤使用）
IFS=',' read -r -a PREFIX_CACHE_RESET_SCENARIOS <<< "$SLA_RESET_PREFIX_SCENARIOS_STR"

if [[ -z "${MODEL_NAME:-}" ]]; then
    echo "Error: --model-path argument is required"
    show_help
    exit 1
fi

if [[ -n "$PREFIX_RATE_ARG" ]]; then
    if [[ ! "$PREFIX_RATE_ARG" =~ ^[0-9]+(\.[0-9]+)?$ ]] || ! awk -v rate="$PREFIX_RATE_ARG" 'BEGIN { exit !(rate + 0 >= 0 && rate + 0 <= 1) }'; then
        echo "Error: --prefix-rate must be a number between 0 and 1 (e.g., 0.6)"
        exit 1
    fi
fi

if [[ -n "$INPUT_LEN_ARG" || -n "$OUTPUT_LEN_ARG" || -n "$NUM_PROMPTS_ARG" || -n "$MAX_CONCURRENCY_ARG" ]]; then
    if [[ -z "$INPUT_LEN_ARG" || -z "$OUTPUT_LEN_ARG" || -z "$NUM_PROMPTS_ARG" || -z "$MAX_CONCURRENCY_ARG" ]]; then
        echo "Error: --input-len, --output-len, --num-prompts, and --max-concurrency must be provided together"
        exit 1
    fi
    CUSTOM_COMBINATIONS=("$INPUT_LEN_ARG $OUTPUT_LEN_ARG $NUM_PROMPTS_ARG $MAX_CONCURRENCY_ARG")
fi

if [[ ${#CUSTOM_COMBINATIONS[@]} -gt 0 ]]; then
    combinations=("${CUSTOM_COMBINATIONS[@]}")
elif [[ "$MODE" != "$SLA_MODE_NAME" ]]; then
    log "未指定测试组合 (-c/--combinations)，默认使用内置 combinations（共 ${#combinations[@]} 组）。"
fi

if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
    if [[ ${#CUSTOM_COMBINATIONS[@]} -gt 0 ]]; then
        log "Mode ${SLA_MODE_NAME} ignores custom combinations and uses the built-in 12 scenarios."
    fi
    if [[ "$SPECULATIVE_INFERENCE_ENABLED" == true ]]; then
        log "Mode ${SLA_MODE_NAME} keeps the same turning-point search flow and uses speed_bench for speculative inference."
    elif [[ -n "${DATASET_ARGS:-}" ]]; then
        log "Mode ${SLA_MODE_NAME} forces --dataset-name random and ignores custom --dataset-args."
    fi
fi

if [[ -n "$BASE_URL" ]]; then
    if [[ -z "${PORT:-}" && -z "${TEST_IP:-127.0.0.1}" ]]; then
        :
    fi
elif [[ -z "${PORT:-}" ]]; then
    echo "Error: either --base-url or --port argument is required"
    show_help
    exit 1
fi

# 获取当前架构
ARCH=$(uname -m)

CURRENT_ACCELERATOR_TYPE=$(detect_accelerator_type)

if [[ -n "$BASE_URL" ]]; then
    BASE_URL_HOST=$(echo "$BASE_URL" | sed -E 's|https?://||' | cut -d':' -f1 | cut -d'/' -f1)
    BASE_URL_PORT=$(echo "$BASE_URL" | sed -E 's|https?://||' | cut -d':' -f2 | cut -d'/' -f1)
    DEFAULT_RESULTS_DIR="./results"
    RESULTS_DIR="${RESULTS_DIR:-$DEFAULT_RESULTS_DIR}"
    RESULTS_DIR="$RESULTS_DIR/${ARCH}_${MODEL_NAME}_${BASE_URL_HOST}_${BASE_URL_PORT}_${TIMESTAMP}_${MODE}"
else
    DEFAULT_RESULTS_DIR="./results"
    RESULTS_DIR="${RESULTS_DIR:-$DEFAULT_RESULTS_DIR}"
    RESULTS_DIR="$RESULTS_DIR/${ARCH}_${MODEL_NAME}_${TEST_IP}_${PORT}_${TIMESTAMP}_${MODE}"
fi

#RESULTS_DIR="./results/${MODEL_NAME}_${TEST_IP}_${PORT}_${TIMESTAMP}_${MODE}"
mkdir -p "$RESULTS_DIR"

GLOBAL_START_TIME=$(date +%s)

{
    echo "==== Benchmark Configuration ===="
    echo "Model:       $MODEL_NAME"
    echo "Tokenizer:   $TOKENIZER_PATH"
    if [[ -n "$BASE_URL" ]]; then
        echo "Base URL:    $BASE_URL"
        if [[ -n "$API_KEY" ]]; then
            echo "API Key:     ***"
        fi
    else
        echo "API IP:      $TEST_IP"
        echo "API Port:    $PORT"
    fi
    echo "Temperature: $TEMPERATURE"
    echo "Accelerator: $CURRENT_ACCELERATOR_TYPE"
    echo "Speculative Inference: $SPECULATIVE_INFERENCE_ENABLED"
    echo "Reset Prefix Cache: $PREFIX_CACHE_RESET"
    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        echo "Reset Prefix Cache Scenarios: $SLA_RESET_PREFIX_SCENARIOS_STR"
    fi
    if [[ -n "$PREFIX_RATE_ARG" ]]; then
        echo "Prefix Rate: ${PREFIX_RATE_ARG}"
    fi
    if [[ -n "$REQUEST_RATE" ]]; then
        echo "Request Rate: $REQUEST_RATE"
    else
        echo "Request Rate: unlimited"
    fi
    echo "Start Time:  $(date)"
    echo "Result Dir:  $RESULTS_DIR"
    echo ""
} > "${RESULTS_DIR}/summary.log"
init_metrics_files

if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
    run_sla_turning_point_mode
else
    run_standard_mode
fi

echo ""
log "核心指标提取完成! 成功处理 $success_count 个文件"
log "结果保存到: $CORE_METRICS_CSV"

TEMP_SUMMARY="${RESULTS_DIR}/temp_summary.log"
GLOBAL_END_TIME=$(date +%s)

{
    echo ""
    echo "==== Benchmark Results Summary ===="
    echo "Start Time: $(date -d @$GLOBAL_START_TIME +'%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r $GLOBAL_START_TIME 2>/dev/null || date)"
    echo "End Time:   $(date)"
    if [[ -n "${GLOBAL_END_TIME:-}" && -n "${GLOBAL_START_TIME:-}" ]]; then
        echo "Total Duration: $(( (GLOBAL_END_TIME - GLOBAL_START_TIME)/60 )) minutes"
    fi
    if [[ -n "$BASE_URL" ]]; then
        echo "Model: $MODEL_NAME | Base URL: $BASE_URL | Temperature: $TEMPERATURE$(if [[ -n "$REQUEST_RATE" ]]; then echo " | Request Rate: $REQUEST_RATE"; else echo " | Request Rate: unlimited"; fi)"
    else
        echo "Model: $MODEL_NAME | IP: $TEST_IP | Port: $PORT | Temperature: $TEMPERATURE$(if [[ -n "$REQUEST_RATE" ]]; then echo " | Request Rate: $REQUEST_RATE"; else echo " | Request Rate: unlimited"; fi)"
    fi
    echo ""
    echo "Column: Time | Input | Output | Prompts | Concurrency | Status | Duration | Result Directory"
    echo "----------------------------------------------------------------------------------------"
} > "$TEMP_SUMMARY"

grep -E "^[0-9]{2}:[0-9]{2}:[0-9]{2}" "${RESULTS_DIR}/summary.log" >> "$TEMP_SUMMARY" 2>/dev/null || true

{
    echo ""
    echo "==== Core Metrics Summary ===="
    echo "核心指标已提取到: $CORE_METRICS_CSV"
    echo "成功处理文件数: $success_count"
    if [[ "$MODE" == "$SLA_MODE_NAME" ]]; then
        echo "SLA 搜索结果已保存到: $SLA_RESULTS_CSV"
    fi
} >> "$TEMP_SUMMARY"

cat "$TEMP_SUMMARY" >> "${RESULTS_DIR}/summary.log"
rm -f "$TEMP_SUMMARY"

echo ""
log "Benchmark completed. All results saved to:"
echo "  $RESULTS_DIR"

if [ "$TEST_FAILED" -ne 0 ]; then
    log "Error: One or more test combinations failed."
    exit 1
fi

