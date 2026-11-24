# A fast interactive shell for the mobile panel. Keep project commands on PATH
# without running slow completion generators every time a terminal is opened.
[[ ! -r /etc/bash.bashrc ]] || source /etc/bash.bashrc
unset NO_COLOR
export COLORTERM=truecolor
if command -v dircolors >/dev/null; then
  if [[ -r "$HOME/.dircolors" ]]; then
    eval "$(dircolors -b "$HOME/.dircolors")"
  else
    eval "$(dircolors -b)"
  fi
  alias ls='ls --color=auto'
  alias grep='grep --color=auto'
  alias fgrep='fgrep --color=auto'
  alias egrep='egrep --color=auto'
fi
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
[[ ! -r "$HOME/.bash_aliases" ]] || source "$HOME/.bash_aliases"
source "$(dirname -- "${BASH_SOURCE[0]}")/shell-integration.bash"
case "$TERM" in
  xterm-color|*-256color)
    PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ' ;;
  *) PS1='\u@\h:\w\$ ' ;;
esac
