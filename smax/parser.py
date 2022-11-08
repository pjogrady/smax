# This file is part of the smax project (http://github.com/baymotion/smax)
# and is copyrighted under GPL v3 or later.

import io
import pkgutil
import re
import smax.log as log
import yapps.grammar
import yapps.parsetree
import yapps.runtime


def load_source(
    filename,
    delimiter="%%",
    start_delimiter=None,
    end_delimiter=None,
):
    """
    Loads a file, replacing all the sections outside the '%%' delimited area
    with blank lines.  For example,
    ...
    ...       (replaced with blank lines)
    ...
    %%        (replaced with a blank line)
    ...
    ...       (left in the output)
    ...
    %%        (replaced with a blank line)
    ...
    ...       (replaced with blank lines)
    ...
    %%        (replaced with a blank line)
    ...
    ...       (more input that's copied to the output)
    ...
    %%        (replaced with a blank line)
    ...
    ...       (replaced with blank lines)
    ...
    This way, syntax errors in the delimited section show up
    with the right line numbers from the original source file.

    You can change the delimiters: Pass a parameter 'delimiter="XY"' to use XY
    instead of %% as delimiters or 'start_delimiter="%{", end_delimiter="%}"'
    to use different delimiters to start and end.
    """
    if start_delimiter is None:
        start_delimiter = delimiter
    if end_delimiter is None:
        end_delimiter = delimiter
    log.trace("load_source filename=%s" % (filename,))
    with open(filename, "rt") as f:
        return load_file(f, start_delimiter, end_delimiter)


def load_file(f, start_delimiter="%%", end_delimiter="%%"):
    lines = []
    while True:
        while True:
            # replace with blanks
            line = f.readline()
            if len(line) == 0:
                break
            lines.append("")
            line = line.rstrip()
            if line == start_delimiter:
                break
        if len(line) == 0:
            break
        while True:
            # copy to the output.
            line = f.readline()
            if len(line) == 0:
                break
            line = line.rstrip()
            if line == end_delimiter:
                break
            lines.append(line)
        if len(line) == 0:
            break
        lines.append("")
    spec = "\n".join(lines)
    return spec


r"""  # noqa: E501
%%

parser state_machine:

    # The scanner returns INDENT and DEDENT by measuring whitespace at the beginning
    # of the line.  To make yapps happy, we provide dummy text it can match,
    # then override the scanner to actually return these tokens as appropriate.
    # INDENTED_CODE fails if a dedent is found; otherwise returns
    # the complete line of text found with the current indent prefix removed.
    token INDENT: "faking out the scanner with something that shouldnt ever match, part 1"
    token DEDENT: "faking out the scanner with something that shouldnt ever match, part 2"
    token INDENTED_CODE: "faking out the scanner with something that shouldnt ever match, part 3"
    token MACHINE: "machine"
    token STATE: "state"
    token PASS: "pass"
    token ENTER: "enter"
    token EXIT: "exit"
    token FROM: "from"
    token IMPORT: "import"
    token IS: "is"
    token START: "\\*"
    token AND: "---"
    token TRANSITION: "->"
    token OPEN_BRACKET: r"\["
    token CLOSE_BRACKET: r"\]"
    token NONBRACKET: r"[^\[\]]*"
    token OPEN_PAREN: r"\("
    token CLOSE_PAREN: r"\)"
    token NONPAREN: r"[^\(\)]*"
    token MS: "ms"
    token S: "s"
    token EOF: "$"
    token UP: r"\^"
    token FLOAT0: r"[0-9]+\.[0-9]*"
    token FLOAT1: r"[0-9]*\.[0-9]+"
    token INT: r"[0-9]+"
    token NAME: r"[\w]+"
    token TOEOL: r".*"
    ignore: r"#.*"      # comments
    ignore: r"[ \r\t\n]+"

    rule machine_spec<<spec>>:
        (   machine<<spec>>
        |   constant<<spec>>
        |   import_<<spec>>      # 'import' is a keyword so we use this alias.
        )*
        EOF
        {{ return spec.spec() }}

    rule constant<<spec>>:
        NAME '=' TOEOL {{ return spec.constant(NAME.strip(), TOEOL.strip()) }}

    rule import_<<spec>>:
        (   IMPORT TOEOL {{ return spec.import_("import %s" % TOEOL.strip()) }}
        |   FROM TOEOL {{ return spec.import_("from %s" % TOEOL.strip()) }}
        )

    rule machine<<spec>>:
        {{ superclass = "object" }}
        MACHINE machine_name [ OPEN_PAREN NAME CLOSE_PAREN {{ superclass = NAME }} ] ':'
        {{ machine = spec.machine(machine_name, superclass) }}
        {{ context = machine.context() }}
        {{ states = [] }}
        INDENT
            ( state_decl<<context>>     {{ states.append(state_decl) }}
            | enter_clause              {{  machine.set_enter(enter_clause) }}
            | exit_clause               {{  machine.set_exit(exit_clause) }}
            | transition<<machine.context()>>
            | AND                       {{ if len(states): context.state_machine(states); states=[]; context=machine.context() }}
            )*
        DEDENT
        {{ if len(states): context.state_machine(states) }}
        {{ machine.check() }}

    rule state_decl<<context>>:
        start STATE
            state_name ':'
                {{ state = context.state(state_name, start) }}
        {{ states = [] }}
        {{ inner_context = state.new_context() }}
        INDENT
            ( transition<<state>>
            | timeout<<state>>
            | state_decl<<inner_context>> {{ states.append(state_decl) }}
            | enter_clause              {{  state.set_enter(enter_clause) }}
            | exit_clause               {{  state.set_exit(exit_clause) }}
            | default_transition<<state>>
            | PASS
            | AND                       {{ if len(states): inner_context.state_machine(states); states=[]; inner_context = state.new_context() }}
            )*
        DEDENT
        {{ if len(states): inner_context.state_machine(states) }}
        {{ return state }}

    rule start:
        {{ r=False }}
        ( START {{ r=True }} )?
        {{ return r }}

    rule transition<<state>>:
        {{ event_args=[ ] }}
        {{ condition=None }}
        {{ state_target=None }}
        {{ code_clause=None }}
        {{ superclasses=[ ] }}
        event_name
            ( OPEN_PAREN event_args CLOSE_PAREN )?
            ( superclass<<superclasses>> )*
            ( OPEN_BRACKET condition CLOSE_BRACKET )?
            ( TRANSITION state_target<<state>> [ ':' code_clause ]
            | ':' (code_clause|PASS)
            )
        {{ state.add_transition(event_name, event_args, superclasses, condition, state_target, code_clause) }}

    rule superclass<<sl>>:
        {{ event_args = None }}
        IS NAME ( OPEN_PAREN event_args CLOSE_PAREN )?
            {{ sl.append( [NAME, event_args] ) }}

    rule event_args:
        {{ args = [] }}
        NAME {{ args.append(NAME) }}
        ( ',' NAME {{ args.append(NAME) }} )*
        {{ return args }}

    rule default_transition<<state>>:
        {{ condition=None }}
        {{ code_clause=None }}
        {{ state_target=None }}
        ( OPEN_BRACKET condition CLOSE_BRACKET )?
        ( TRANSITION state_target<<state>> [ ':' code_clause ] | ':' (code_clause|PASS) )
        {{ state.default_transition(condition, state_target, code_clause) }}

    rule timeout<<state>>:
        {{ code_clause = None }}
        {{ condition = None }}
        {{ state_target = None }}
        time_spec<<state>>
        ( OPEN_BRACKET condition CLOSE_BRACKET )?
        [ TRANSITION state_target<<state>>] [':' (code_clause|PASS)]
        {{ state.add_timeout(time_spec, condition, state_target, code_clause) }}

    rule time_spec<<state>>:
        (   MS OPEN_PAREN expr CLOSE_PAREN {{ return state.timeout_ms(expr) }}
        |   S OPEN_PAREN expr CLOSE_PAREN {{ return state.timeout_s(expr) }}
        )

    rule float:
        (   INT {{ r = float(INT) }}
        |   FLOAT0 {{ r = float(FLOAT0) }}
        |   FLOAT1 {{ r = float(FLOAT1) }}
        )
        {{ return r }}

    rule condition:
        _condition<<[]>>
        {{ return "".join(_condition) }}

    rule _condition<<l>>:
        ( NONBRACKET {{ l.append(NONBRACKET) }} )?
        ( OPEN_BRACKET condition<<[]>> CLOSE_BRACKET
            {{ l.append("["); l.extend(condition); l.append("]") }}
        )*
        {{ return l }}

    rule expr:
        {{ l = [] }}
        ( _expr<<[]>> {{ l.append("".join(_expr)) }} )*
        {{ return "".join(l) }}

    rule _expr<<l>>:
        (   NONPAREN    {{ l.append(NONPAREN) }}
        |   OPEN_PAREN _expr<<[]>> CLOSE_PAREN
                {{ l.append("("); l.extend(_expr); l.append(")") }}
        )
        {{ return l }}

    rule enter_clause:
        ENTER ':' code_clause
        {{ return code_clause }}

    rule exit_clause:
        EXIT ':' code_clause
        {{ return code_clause }}

    rule code_clause:
        ( simple_code_clause {{ return simple_code_clause }}
        | indented_code_clause {{ return indented_code_clause }}
        )

    rule simple_code_clause:
        TOEOL {{ return [ TOEOL.strip() ] }}

    rule indented_code_clause:
        INDENT {{ r = [ ] }}
            ( INDENTED_CODE {{ r.append(INDENTED_CODE) }} )+
        DEDENT {{ return r }}

    rule event_name:
        NAME {{ return NAME }}

    rule machine_name:
        NAME {{ return NAME }}

    rule state_name:
        NAME {{ return NAME }}

    rule state_target<<state>>:
        {{ r = [ ] }}
        ( UP {{ r.append(UP) }} )*
        NAME  {{ r.append(NAME) }}
        ( r'\.' NAME {{ r.append(NAME) }} )*
        {{ return r }}

%%
"""


class Buffer:
    def __init__(self):
        self._buffer = []

    def write(self, msg):
        self._buffer.append(msg)


def load_parser():
    source_data = pkgutil.get_data(__name__, "parser.py").decode("utf-8")
    source_file = io.StringIO(source_data)
    source = load_file(source_file)
    scanner = yapps.grammar.ParserDescriptionScanner(source, filename=__file__)
    parser = yapps.grammar.ParserDescription(scanner)
    # monkey-patch the writer so we catch the python code
    t = yapps.runtime.wrap_error_reporter(parser, "Parser")
    t.output = Buffer()
    t.postparser = "\n\n"
    t.generate_output()
    parser_python = "".join(t.output._buffer)
    if False:
        with open("parser-out", "wt") as f:
            f.write(parser_python)
    # run the generated python code.
    exec(parser_python, globals())


load_parser()


class Scanner(state_machineScanner):  # noqa: F821
    def __init__(self, *args, **kwargs):
        super(Scanner, self).__init__(*args, **kwargs)
        self._indent = [0]
        self._eof = None
        self._spaces = re.compile("\n([ ]*)")
        self._blank_line = re.compile("\n([ ]*(#[^\n]*)?)\n")
        self._indented_code = re.compile("\n([ ]*)([^\n]*)")

    def token(self, restrict, context=None):
        log.trace("restrict=%s, pos=%s." % (restrict, self.get_pos()))
        # If we're looking for INDENTED_CODE, return this if the
        # input text indent >= current indent level.
        if "INDENTED_CODE" in restrict:
            m = self._indented_code.match(self.input, self.pos)
            log.trace("Checking indented code, m=%s." % (m,))
            if m:
                indent = len(m.group(1))
                code = m.group(2)
                log.trace(
                    "indent=%u (was %u), code=%s."
                    % (
                        indent,
                        self._indent[-1],
                        code,
                    )
                )
                if indent >= self._indent[-1]:
                    code_spaces = " " * (indent - self._indent[-1])
                    line = code_spaces + code
                    token = yapps.runtime.Token(
                        "INDENTED_CODE",
                        line,
                        self.get_pos(),
                    )
                    log.trace("token=%s." % (token,))
                    self.pos += len(m.group(0))
                    return token
        # If they're looking for INDENT or DEDENT,
        # see if we're at the end-of-line followed by some
        # spaces; if the indent level changes, then pass that
        # token back up.  We'll consider EOF to be a series of
        # DEDENT if we're looking for dedent too.
        if (
            ("DEDENT" in restrict)
            and (self.pos >= len(self.input))
            and len(self._indent)
        ):
            self._indent.pop()
            token = yapps.runtime.Token("DEDENT", 0, self.get_pos())
            return token
        if ("INDENT" in restrict) or ("DEDENT" in restrict):
            while True:
                # skip blank lines and comments
                m = self._blank_line.match(self.input, self.pos)
                if m:
                    self.pos += len(m.group(0)) - 1  # KEEP THE LAST NEWLINE.
                else:
                    break
            m = self._spaces.match(self.input, self.pos)
            log.trace(
                "Checking in/dedent, m=%s (length=%s)."
                % (m, "n/a" if m is None else len(m.group(1)))
            )
            if m:
                indent = len(m.group(1))
                log.trace("indent=%u." % indent)
                if indent > self._indent[-1]:
                    self._indent.append(indent)
                    token = yapps.runtime.Token(
                        "INDENT",
                        indent,
                        self.get_pos(),
                    )
                    log.trace("token=%s." % (token,))
                    return token
                if indent < self._indent[-1]:
                    self._indent.pop()
                    token = yapps.runtime.Token(
                        "DEDENT",
                        indent,
                        self.get_pos(),
                    )
                    log.trace("token=%s." % (token,))
                    return token
        token = super(Scanner, self).token(restrict, context)
        log.trace("token=%s." % (token,))
        return token


class Parser(state_machine):  # noqa: F821
    def __init__(self, *args, **kwargs):
        super(Parser, self).__init__(*args, **kwargs)

    def parse(self):
        spec = Specification()
        return self.machine_spec(spec)


class SyntaxError(Exception):
    pass


class SmaxException(Exception):
    """
    Used for semantic errors in the state machine spec.
    """

    pass


class Transition(object):
    def __init__(self, state, event, superclasses, condition, target, code):
        self.state = state
        self.event = event
        self.condition = condition
        self.target = target
        self.code = code
        self.superclasses = superclasses

    def find(self, state):
        return "target=%s/%s." % (state.name, self.target)


class Timeout(object):
    def __init__(self, state, time_spec, condition, target, code):
        self.state = state
        self.time_spec = time_spec
        self.condition = condition
        self.target = target
        self.code = code


class TimeSpec(object):
    def __init__(self, expr, scale):
        self.timeout = expr
        self.scale = scale


class Event(object):
    def __init__(self, event, event_args, superclasses):
        self.name = event
        self.args = event_args
        self.superclasses = []
        self._superclasses = {}
        self.merge_superclasses(superclasses)

    def merge_superclasses(self, superclasses):
        for superclass in superclasses:
            name, args = superclass
            existing_args = self._superclasses.get(name, None)
            if existing_args:
                if len(args) != len(existing_args):
                    raise SmaxException(
                        "Incompatible parameter list with %s superclass %s."
                        % self.name,
                        name,
                    )
                continue
            self.superclasses.append(superclass)
            self._superclasses[name] = args


class State(object):
    def __init__(self, machine, parent, name, start):
        self._machine = machine
        self.parent = parent
        self.name = name
        self.start = start
        self.enter = []
        self.exit = []
        self.timeouts = []
        self.transitions = []
        self.inner_states = []
        self._all_inner_states = []
        self._state = {}
        self._events = {}
        self.events = []
        self._default_transition = []

    def check(self, machine):
        # make sure all our inner states have exactly one start state.
        for sl in self.inner_states:
            start_found = False
            for s in sl:
                if s.start and start_found:
                    raise SmaxException(
                        "Multiple start states found in %s." % self.name,
                    )
                if s.start:
                    start_found = True
            if not start_found:
                raise SmaxException("No start states found in %s." % self.name)
        u = [self.name]
        d = [self.name]
        s = self
        while s.parent:
            p = s.parent
            u.insert(0, p.name)
            d.insert(0, p.name)
            for n, l in enumerate(p.inner_states):
                if s in l:
                    u.insert(1, "%d" % n)
                    break
            s = p
        self.full_name = "_".join(u)
        self.dot_name = ".".join(d)
        self.name_list = d
        self.array_name = self.full_name + "_name"
        log.trace(
            "%s: full_name=%s, dot_name=%s."
            % (
                self,
                self.full_name,
                self.dot_name,
            )
        )
        target_name = "n/a"
        n = 0  # in case transitions is empty
        for n, t in enumerate(self.transitions):
            log.trace("t=%s, target=%s." % (t, t.target))
            t.n = n
            if t.target is None:
                continue
            m = self
            i = 0
            while t.target[i] == "^":
                if not m.parent:
                    raise SmaxException("Cannot go up from %s." % (m.name,))
                m = m.parent
                log.trace("t.target[%d] == '^'; going up to %s." % (i, m.name))
                i += 1
            # assert len(t.target)==(i + 1)
            try:
                # Is the target state one of our children?
                # If so then don't unconfigure ourselves.
                q = m._state[t.target[i]]
                t.unconfigure = False
            except KeyError:
                # Is the target state one of our parent's children?
                if not m.parent:
                    raise SmaxException("Can't find target state %s." % (t.target[i],))
                q = m.parent._state[t.target[i]]
                t.unconfigure = True
            log.trace("t.target[%d] found %s." % (i, q.name))
            i += 1
            while i < len(t.target):
                q = q._state[t.target[i]]
                log.trace("t.target[%d] found %s." % (i, q.name))
                i += 1
            t.target_state = q
            target_name = q.name
        for n, t in enumerate(self.timeouts):
            log.trace("t=%s, target=%s." % (t, target_name))
            t.n = n
            if t.target is None:
                continue
            m = self.parent
            i = 0
            while t.target[i] == "^":
                m = m.parent
                i += 1
            assert len(t.target) == (i + 1)
            t.target_state = m._state[t.target[i]]
            t.unconfigure = True

    def _full_name(self):
        if self.parent:
            r = self.parent._full_name()
            if self.parent.inner_states:
                for n, l in self.parent.inner_states:
                    if self in l:
                        r.append("%d", n)
                        break
        r.append(self.name)
        return r

    def set_enter(self, enter):
        self.enter = enter

    def set_exit(self, exit):
        self.exit = exit

    def add_transition(
        self,
        event_name,
        event_args,
        superclasses,
        condition,
        state_target,
        code_clause,
    ):
        ev = self._machine.event(event_name, event_args, superclasses)
        t = Transition(
            self,
            ev,
            superclasses,
            condition,
            state_target,
            code_clause,
        )
        self.transitions.append(t)
        self.add_event(ev)

    def default_transition(self, condition, state_target, code_clause):
        t = Transition(self, None, [], condition, state_target, code_clause)
        if condition is None:
            self._default_transition.append(t)
        self.transitions.append(t)

    def add_event(self, ev):
        self._events[ev] = ev
        self.events.append(ev)
        if self.parent:
            self.parent.add_event(ev)

    def new_context(self):
        return self

    def timeout_s(self, expr):
        return TimeSpec(expr, "s")

    def timeout_ms(self, expr):
        return TimeSpec(expr, "ms")

    def add_timeout(self, time_spec, condition, state_target, code_clause):
        t = Timeout(self, time_spec, condition, state_target, code_clause)
        self.timeouts.append(t)

    def state(self, name, start):
        state_name = name
        log.trace("state name=%s start=%s." % (state_name, start))
        # is "state_name" already in self._state?
        if state_name in self._state:
            raise SyntaxError("State %s is duplicate." % (state_name,))
        s = State(self._machine, self, name, start)
        log.trace("new state=%s, parent=%s." % (s.name, s.parent.name))
        self._state[state_name] = s
        return s

    def state_machine(self, states):
        n = len(self.inner_states)
        for i, s in enumerate(states):
            s.n = n
            s.or_with = states
            s.or_n = i
        self.inner_states.append(states)
        self._all_inner_states.extend(states)

    def all_states_depth_first(self):
        if not self._all_inner_states:
            return [self]
        r = []
        for m in self.inner_states:
            for i in m:
                r.extend(i.all_states_depth_first())
        r.append(self)
        return r

    # breadth first
    def all_states(self):
        r = [self]
        for m in self.inner_states:
            for i in m:
                r.extend(i.all_states())
        return r


class Machine(State):
    def __init__(self, name, superclass):
        super(Machine, self).__init__(self, None, name, True)
        self.superclass = superclass
        self._event = {}

    def context(self):
        return self

    def event(self, event, event_args, superclasses):
        event_name = event
        log.trace(
            "event_name=%s, event_args=%s, superclasses=%s."
            % (event_name, event_args, superclasses)
        )
        try:
            ev = self._event[event_name]
            if len(event_args) and (len(event_args) != len(ev.args)):
                raise SyntaxError(
                    "Event %s with different argument list.",
                    event_name,
                )
            ev.merge_superclasses(superclasses)
        except KeyError:
            # make a new event.
            ev = Event(event, event_args, superclasses)
            self._event[event_name] = ev
        return ev

    def check(self, machine=None):
        self.event_list = list(self._event.values())
        self.event_list.sort(key=lambda ev: ev.name)
        super(Machine, self).check(self)
        for s in self.all_states():
            if s != self:
                s.check(self)


class Specification:
    def __init__(self):
        log.trace("new Specification.")
        self._output = []

    def constant(self, name, value):
        log.trace("new constant, name=%s, value=%s." % (name, value))
        self._output.append({"constant": {"name": name, "value": value}})

    def import_(self, sequence):
        log.trace("new import, sequence=%s." % (sequence,))
        self._output.append({"import": sequence})

    def machine(self, name, superclass):
        m = Machine(name, superclass)
        self._output.append({"machine": m})
        return m

    def spec(self):
        return self._output
