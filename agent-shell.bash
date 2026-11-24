# Runs the agent as a job of an interactive shell. A session-leader launcher
# leaves the agent in an orphaned process group, where the kernel discards
# Ctrl+Z. As a job, Ctrl+Z suspends it and `fg` resumes it.
source "$(dirname -- "${BASH_SOURCE[0]}")/managed-shell.bash"
set -m
__mobile_agent=$TERMINAL_MOBILE_AGENT
unset TERMINAL_MOBILE_AGENT
__mobile_record_exit() {
  local code=$?
  [[ -n ${__mobile_agent_pid:-} ]] || return 0
  kill -0 "$__mobile_agent_pid" 2>/dev/null && return 0
  # 127 means fg already reaped it; $code then holds the agent's status.
  wait "$__mobile_agent_pid" 2>/dev/null
  local waited=$?
  (( waited == 127 )) || code=$waited
  tmux set-option -w -t "$TMUX_PANE" @mobile_exit_code "$code" 2>/dev/null
  tmux set-option -w -t "$TMUX_PANE" @mobile_exit_pid "$__mobile_agent_pid" 2>/dev/null
  __mobile_agent_pid=
}
PROMPT_COMMAND="__mobile_record_exit${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
eval "$__mobile_agent &"
__mobile_agent_pid=$!
fg %% >/dev/null
