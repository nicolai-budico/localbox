# Bash completion for localbox
# Handles colon-separated targets like projects:be:authserver

_localbox_completion() {
    local IFS=$'\n'
    local cur prev words cword
    
    # Use _get_comp_words_by_ref if available (handles colons properly)
    if declare -F _get_comp_words_by_ref &>/dev/null; then
        _get_comp_words_by_ref -n : cur prev words cword
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    fi

    # Get completions from Click
    local response
    response=$(env COMP_WORDS="${words[*]}" COMP_CWORD=$cword _LOCALBOX_COMPLETE=bash_complete localbox 2>/dev/null)

    COMPREPLY=()
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        if [[ $type == 'plain' ]]; then
            COMPREPLY+=("$value")
        elif [[ $type == 'dir' ]]; then
            compopt -o dirnames
        elif [[ $type == 'file' ]]; then
            compopt -o default
        fi
    done

    # Handle colon completions (trim prefix that bash already has)
    if declare -F __ltrim_colon_completions &>/dev/null; then
        __ltrim_colon_completions "$cur"
    fi

    return 0
}

complete -o nosort -F _localbox_completion localbox
