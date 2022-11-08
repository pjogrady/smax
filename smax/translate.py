# This file is part of the smax project (http://github.com/baymotion/smax)
# and is copyrighted under GPL v3 or later.

# translate.py - Smax module which generates code.

import jinja2
import smax.log as log
import smax.parser
import time
import sys

environment = jinja2.Environment()


def machine(m):
    # we store some parameters in the state objects.
    for s in m.all_states():
        s._transition_methods = []
    t = environment.from_string(
        r"""
class {{ machine.name }}({{machine.superclass}}):
    # Make some printable strings to help diagnostics.
    {%- for state in machine.all_states() %}
    {{state.array_name}} = {{state.name_list|as_list}}
    {{state.full_name}} = "{{state.dot_name}}"
    {%- endfor %}{# state in machine.all_states() #}
    def __init__(self, reactor, debug_enable=False):
        self._reactor = reactor
        self._state = { }
        self._state_machine_debug_enable = debug_enable
        self._is_valid = False
        self._busy = False
    def _state_machine_debug(self, msg):
        if self._state_machine_debug_enable:
            print(
                "DEBUG -- %s, state=%s." % (msg, ",".join(self._state.keys()))
            )
    # for diagnostic only
    def _state_machine_enter(self, state_name):
        self._state_machine_debug("Entering %s" % ".".join(state_name))
    # for diagnostic only
    def _state_machine_exit(self, state_name):
        self._state_machine_debug("Exiting %s" % ".".join(state_name))
    # for diagnostic only
    def _state_machine_handle(self, state_name, event_name, *args):
        self._state_machine_debug(
            "%s handling %s" % (".".join(state_name), event_name)
        )
    def _state_machine_timeout(self, state_name, time_spec):
        self._state_machine_debug(
            "%s timed out after %s" % (".".join(state_name), time_spec)
        )
    def _state_machine_ignored(self, event_name, *args):
        self._state_machine_debug("Ignored %s" % event_name)
    def _state_machine_call_after_s(self, seconds, callback, context):
        self._state_machine_debug(
            "Scheduling %s timeout after %s seconds." % (context, seconds)
        )
        return self._reactor.after_s(seconds, callback)
    def _state_machine_call_after_ms(self, ms, callback, context):
        self._state_machine_debug(
            "Scheduling %s timeout after %s ms." % (context, ms)
        )
        return self._reactor.after_ms(ms, callback)
    def _state_machine_cancel_timeout(self, handle):
        return self._reactor.cancel_after(handle)
    def _record_state(self, state, timeouts):
        self._state[state] = timeouts
    def _unrecord_state(self, state):
        return self._state.pop(state)
    def _in_state(self, state):
        return state in self._state
    def start(self):
        if self._is_valid:
            raise RuntimeError("{{machine.name}} is already running")
        self.call(self._{{machine|munge("enter")}})
        self._is_valid = True
    def end(self):
        self.call(self._{{machine|munge("unconfigure")}})
    def call(self, cb, *args):
        self._reactor.call(cb, *args)
    # events
    {%- for ev in machine.event_list %}
    def {{ev.name}}({{ev.args|insert("self")|join(", ")}}):
        m = lambda self: self._{{machine.full_name}}_{{ev.name}}(
            {{ev.args|join(", ")}}
        )
        if self._busy:
            raise RuntimeError("{{machine.name}} recursive events (via a call to {{ev.name}}) is not supported.")
        try:
            self._busy = True
            return self._reactor._run_event(self, m)
        finally:
            self._busy = False
    {%- endfor %}{# ev in machine.event_list #}
    # states
    {%- for state in machine.all_states() %}
    def _{{state|munge("enter")}}(self):
        {%- if state.parent %}
        if not self._in_state(self.{{state.parent.full_name}}):
            self._{{state.parent|munge("configure")}}(
                [{{state|configure_list|join(", ")}}],
            )
        else:
            self._{{state|munge("configure")}}()
        {%- else %}{# state.parent #}
        self._{{state|munge("configure")}}()
        {%- endif %}{# state.parent #}
    def _{{state|munge("configure")}}(self, configurators=None):
        {%- set condition=["if"] %}
        {%- for or_peer in state.or_with %}
        {{condition[0]}} self._in_state(self.{{or_peer.full_name}}):
            self._{{or_peer|munge("unconfigure")}}()
        {%- set _ = condition.append("elif" if condition.pop() else "if") %}
        {%- endfor %}{# or_peer in self.or_with #}
        {%- if state.parent %}
        if not self._in_state(self.{{state.parent.full_name}}):
            self._state_machine_debug("Not in {{state.parent.full_name}}")
            self._{{state.parent|munge("configure")}}(
                [{{state|configure_list|join(", ")}}],
            )
            return
        {%- endif %}{# state.parent #}
        self._state_machine_enter(self.{{state.array_name}})
        {{-state|configure|indent(8)}}
        {%- if state.timeouts %}
        self._record_state(self.{{state.full_name}}, [
        {%- for t in state.timeouts %}
            self._state_machine_call_after_{{t.time_spec.scale}}(
                {{t.time_spec.timeout}},
                self._{{state|munge("timeout", loop.index0)}},
                self.{{state.full_name}},
            ),
        {%- endfor %}{# t in state.timeouts #}
            ])
        {%- else %}{# state.timeouts #}
        self._record_state(self.{{state.full_name}}, [])
        {%- endif %}{# state.timeouts #}
        if configurators is None:
            configurators = [{{state|child_list|join(", ")}}]
        for c in configurators:
            c()
        {{-state|transitions()|indent(8)}}
    def _{{state|munge("unconfigure")}}(self):
        {%- for sl in state.inner_states %}
        {%- set condition=["if"] %}
        {%- for s in sl %}
        {{condition[0]}} self._in_state(self.{{s.full_name}}):
            self._{{s|munge("unconfigure")}}()
        {%- set _ = condition.append("elif" if condition.pop() else "if") %}
        {%- endfor %}{# s in sl #}
        {%- endfor %}{# sl in state.inner_states #}
        self._state_machine_exit(self.{{state.array_name}})
        timeout_list = self._unrecord_state(self.{{state.full_name}})
        for t in timeout_list:
            self._state_machine_cancel_timeout(t)
        {{ state.exit|code("exit")|indent(8) }}
    {%- for event in machine.event_list %}
    {%- if event in state._events %}
    def _{{state.full_name}}_{{event.name}}(
        {{event.args|insert("self")|join(", ")}},
    ):
        if not self._is_valid:
            raise RuntimeError(
                "{{event.name}}: {{machine.name}} is not running",
            )
        r = False
        # Check inner states (if any)
        {%- for sl in state.inner_states %}
        {%- set condition=["if"] %}
        {%- for s in sl %}
        {%- if event in s._events %}
        {{condition[0]}} self._in_state(self.{{s.full_name}}):
            r = \
              self._{{s.full_name}}_{{event.name}}({{event.args|join(", ")}}) \
              or r
        {%- set _ = condition.append("elif" if condition.pop() else "if") %}
        {%- endif %}{# event in s._events #}
        {%- endfor %}{# s in sl #}
        {%- endfor %}{# sl in state.inner_states #}
        if r:
            return True
        {{-state|transitions(event)|indent(8)}}
        {%- for name, args in event.superclasses %}
        # superclass: {{name}} {{args}}
        if not r:
            r = self._{{machine.name}}_{{name}}({{args|join(", ")}})
        {%- endfor %}{# superclass in event.superclasses #}
        {%- if not state.parent %}
        if not r:
            self._state_machine_ignored(
                {{args|insert("\"%s\"" % event.name)|join(", ")}},
            )
        {%- endif %}{# not state.parent #}
        return r
    {%- endif %}{# event in state._events #}
    {%- endfor %}{# event in machine.event_list #}
    {%- for timeout in state.timeouts %}
    def _{{state|munge("timeout", loop.index0)}}(self):
        {%- if timeout.condition %}
        if not ({{timeout.condition}}):
            return
        {%- endif %}{# timeout.condition #}
        self._state_machine_timeout(
            self.{{state.array_name}},
            "{{timeout.time_spec.timeout}}{{timeout.time_spec.scale}}",
        )
        {{-timeout|goto|indent(8)}}
    {%- endfor %}{# timeout in state.timeouts #}
    {%- for transition in state._transition_methods %}
    {{- transition|transition_method|indent(4) }}
    {%- endfor %}{# transition in state._transition_methods #}
    {%- endfor %}{# state in machine.all_states() #}
"""
    )
    r = t.render(machine=m)
    return r


def transitions(state, event=None):
    t = environment.from_string(
        r"""
{%- if transition.condition %}
if {{transition.condition}}:
    self._state_machine_handle({{event_args|join(", ")}})
    if \
        {{-transition|goto|indent(4)}}:
        return True
{%- else %}{# transition.condition #}
self._state_machine_handle({{event_args|join(", ")}})
r = \
{{-transition|goto|indent(0)}}
{%- endif %}{# transition.condition #}
"""
    )
    r = []
#   already_has_default_transition = False
    for transition in state.transitions:
        if transition.event == event:
            event_args = ["self." + state.full_name + "_name"]
            if event:
                event_args.append('"%s"' % event.name)
                event_args.extend(['"%s"' % s for s in event.args])
            else:
                event_args.append(None)
                # there should only be at most one of these.
#               assert not already_has_default_transition
#               if not transition.condition:
#                   already_has_default_transition = True
            r.append(
                t.render(
                    transition=transition,
                    state=state,
                    event_args=event_args,
                )
            )
    return "".join(r)


def configure(state):
    t = environment.from_string(
        r"""
{{state.enter|code("enter")}}
"""
    )
    return t.render(state=state)


def timeouts(state):
    r = []
    for n, t in enumerate(state.timeouts):
        r.append(
            "self._state_machine_call_after_%s(%s, self._%s)"
            % (
                t.time_spec.scale,
                t.time_spec.timeout,
                munge(state, "timeout", n),
            )
        )
    return r


def code(c, context):
    if not c or (len(c) == 0):
        return "pass # (no %s code was specified)" % (context,)
    return "\n".join(c)


def goto(transition):
    state = transition.state
    if transition not in state._transition_methods:
        state._transition_methods.append(transition)
    event = hasattr(transition, "event")
    args = []
    if event and transition.event:
        args.extend(transition.event.args)
    t = environment.from_string(
        r"""
{{transition_method}}({{args|join(", ")}})
"""
    )
    return t.render(
        transition=transition,
        args=args,
        transition_method="self._%s" % transition_name(transition),
    )


def transition_method(transition):
    event = hasattr(transition, "event")
    args = []
    if event:
        if transition.event:
            args.extend(transition.event.args)
    t = environment.from_string(
        r"""
def _{{transition|transition_name}}({{args|insert("self")|join(", ")}}):
    {%- if transition.unconfigure %}
    self._{{transition.state|munge("unconfigure")}}()
    {%- endif %}{# transition.unconfigure #}
    # transition code
    {{ transition.code|code("transition")|indent(4) }}
    {%- if transition.target_state %}
    self._{{transition.target_state|munge("configure")}}()
    return True
    {%- else %}{# transition.target_state #}
    return False
    {%- endif %}{# transition.target_state #}
"""
    )
    return t.render(transition=transition, args=args)


def munge(state, context, index=None):
    log.trace(
        "munge, state=%s, context=%s, index=%s."
        % (
            state.name,
            context,
            index,
        ),
    )
    r = [state.full_name, context]
    if index is not None:
        r.append("%s" % index)
    return "_".join(r)


def transition_name(transition):
    timeout = not hasattr(transition, "event")
    state = transition.state
    return "%s_%s_%s" % (
        state.full_name,
        "timedout" if timeout else "transition",
        transition.n,
    )


def insert(sequence, s):
    r = [s]
    r.extend(sequence)
    return r


# Returns a list of methods that the parent
# will call to properly set itself up.
def configure_list(state):
    sequence = []
    for sl in state.parent.inner_states:
        if state in sl:
            sequence.append("self._%s" % munge(state, "configure"))
            continue
        for s in sl:
            if s.start:
                sequence.append("self._%s" % munge(s, "configure"))
    return sequence


def child_list(state):
    sequence = []
    for sl in state.inner_states:
        for s in sl:
            if s.start:
                sequence.append("self._%s" % munge(s, "configure"))
    return sequence


def as_list(sequence):
    r = ['"%s"' % i for i in sequence]
    return "[%s]" % ",".join(r)


environment.filters["machine"] = machine
environment.filters["munge"] = munge
environment.filters["insert"] = insert
environment.filters["configure"] = configure
environment.filters["goto"] = goto
environment.filters["timeouts"] = timeouts
environment.filters["code"] = code
environment.filters["transitions"] = transitions
environment.filters["configure_list"] = configure_list
environment.filters["child_list"] = child_list
environment.filters["transition_name"] = transition_name
environment.filters["transition_method"] = transition_method
environment.filters["as_list"] = as_list


def parse(source, filename):
    scanner = smax.parser.Scanner(source, filename=filename)
    p = smax.parser.Parser(scanner)
    s = p.parse()
    spec = {
        "program_name": sys.argv[0],
        "run_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_name": filename,
        "spec": s,
    }
    return spec


def generate_python(spec):
    # Generate the output.
    t = environment.from_string(
        r"""
# Generated by {{ program_name }} from {{ source_name }}.
{%- for s in spec %}
{#- Constant? #}
{%- if "constant" in s %}
{{ s.constant.name }} = {{ s.constant.value }}
{%- endif %}
{#- Import? #}
{%- if "import" in s %}
{{ s.import }}
{%- endif %}
{#- Machine? #}
{%- if "machine" in s %}
{{ s.machine|machine }}
{%- endif %}
{%- endfor %}
"""
    )
    s = t.render(spec) + "\n"
    return s


def translate(source, filename, yaml_filename=None):
    spec = parse(source, filename)
    code = generate_python(spec)
    return spec, code
