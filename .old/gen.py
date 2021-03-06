from functools import reduce, singledispatch
from dataclasses import dataclass, field
from typing import Optional, Dict, Union, List

from vm import Val, Instr, InstrKind, Program
from common import (Node, Stmt, Block, Expr, Lit, Int, Var, FnCall, FnDef,
                    VarDecl, WhileLoop, Assign)


_TOS_ADDR_PTR = 0
_STACK_BASE = 8
_DUMMY_ADDR = -9999999


class GenError(Exception):
    pass


@dataclass
class Namespace:
    stack: List[Dict[str, int]] = field(default_factory=list)
    _max_depth: int = 0

    def get(self, name: str) -> int:
        for ns in reversed(self.stack):
            if name in ns:
                return ns[name]
        raise GenError(f'Unknown identifier: {name}')

    def add(self, names: List[str], stack_size: int) -> 'Namespace':
        for name in names:
            assert name not in self.stack[-1]
            depth = self.depth()
            self.stack[-1][name] = depth + 1
            self._max_depth = max(self._max_depth, depth)
        return self

    def depth(self) -> int:
        return sum(len(ns) for ns in self.stack)

    def push(self) -> None:
        self.stack.append(dict())

    def pop(self) -> None:
        self.stack.pop()


@dataclass
class Unit:
    instrs: Program = field(default_factory=Program)
    labels: Dict[str, int] = field(default_factory=dict)
    jumps: Dict[int, str] = field(default_factory=dict)
    comments: Dict[int, str] = field(default_factory=dict)
    inline_comments: Dict[int, str] = field(default_factory=dict)

    _next_label_id: int = -1

    @classmethod
    def new_label(self) -> str:
        self._next_label_id += 1
        return f'__{self._next_label_id}'

    def _add_instr(self, instr_kind: InstrKind, arg: Optional[Val] = None
                   ) -> 'Unit':
        self.instrs.append(Instr(instr_kind, arg))
        return self

    def insert(self, unit: 'Unit') -> 'Unit':
        addr_offset = len(self.instrs)
        offset_labels = {name: addr + addr_offset
                         for name, addr in unit.labels.items()}
        offset_jumps = {addr + addr_offset: name
                        for addr, name in unit.jumps.items()}
        if self.instrs.here in self.comments and 0 in unit.comments:
            unit.comments[0] = (self.comments[self.instrs.here] + '\n' +
                                unit.comments[0])
        offset_comments = {addr + addr_offset: comment
                           for addr, comment in unit.comments.items()}
        if (self.instrs.here in self.inline_comments
                and 0 in unit.inline_comments):
            unit.inline_comments[0] = (self.inline_comments[self.instrs.here]
                                       + '; ' + unit.inline_comments[0])
        items = unit.inline_comments.items()
        offset_inline_comments = {addr + addr_offset: comment
                                  for addr, comment in items}
        self.labels.update(offset_labels)
        self.jumps.update(offset_jumps)
        self.comments.update(offset_comments)
        self.inline_comments.update(offset_inline_comments)
        self.instrs.extend(unit.instrs)
        return self

    def link(self) -> 'Unit':
        for addr, name in self.jumps.items():
            if name not in self.labels:
                raise GenError(f'Unknown label: {name}')
            instr = self.instrs[addr]
            assert instr.kind in [InstrKind.Jmp, InstrKind.JmpF,
                                  InstrKind.JmpT, InstrKind.Call]
            assert instr.arg == _DUMMY_ADDR
            instr.arg = self.labels[name] - 1
        return self

    def label(self, name: str) -> 'Unit':
        self.labels[name] = len(self.instrs)
        return self

    def comment(self, comment: str) -> 'Unit':
        idx = self.instrs.here
        if idx not in self.comments:
            self.comments[self.instrs.here] = comment
        else:
            self.comments[idx] += '\n' + comment
        return self

    def inline_comment(self, comment: str) -> 'Unit':
        idx = self.instrs.here - 1
        if idx not in self.inline_comments:
            self.inline_comments[idx] = comment
        else:
            self.inline_comments[idx] += '; ' + comment
        return self

    def noop(self) -> 'Unit':
        return self._add_instr(InstrKind.Pop)

    def halt(self) -> 'Unit':
        return self._add_instr(InstrKind.Halt)

    def rot(self) -> 'Unit':
        return self._add_instr(InstrKind.Rot)

    def dup(self) -> 'Unit':
        return self._add_instr(InstrKind.Dup)

    def load(self) -> 'Unit':
        return self._add_instr(InstrKind.Load)

    def store(self) -> 'Unit':
        return self._add_instr(InstrKind.Store)

    def add(self) -> 'Unit':
        return self._add_instr(InstrKind.Add)

    def sub(self) -> 'Unit':
        return self._add_instr(InstrKind.Sub)

    def shl(self) -> 'Unit':
        return self._add_instr(InstrKind.Shl)

    def shr(self) -> 'Unit':
        return self._add_instr(InstrKind.Shr)

    def and_(self) -> 'Unit':
        return self._add_instr(InstrKind.And)

    def or_(self) -> 'Unit':
        return self._add_instr(InstrKind.Or)

    def call(self, name: str) -> 'Unit':
        self.jumps[self.instrs.here] = name
        return self._add_instr(InstrKind.Call, _DUMMY_ADDR)

    def ret(self) -> 'Unit':
        return self._add_instr(InstrKind.Ret)

    def st(self) -> 'Unit':
        return self._add_instr(InstrKind.St)

    def jmp(self, name: str) -> 'Unit':
        self.jumps[self.instrs.here] = name
        return self._add_instr(InstrKind.Jmp, _DUMMY_ADDR)

    def jmp_f(self, name: str) -> 'Unit':
        self.jumps[self.instrs.here] = name
        return self._add_instr(InstrKind.JmpF, _DUMMY_ADDR)

    def jmp_t(self, name: str) -> 'Unit':
        self.jumps[self.instrs.here] = name
        return self._add_instr(InstrKind.JmpT, _DUMMY_ADDR)

    def push(self, arg: Val) -> 'Unit':
        return self._add_instr(InstrKind.Push, arg)

    def pop(self) -> 'Unit':
        return self._add_instr(InstrKind.Pop)

    def print(self) -> 'Unit':
        return self._add_instr(InstrKind.Print)

    def incr_tos(self, offset: Val) -> 'Unit':
        if offset == 0:
            return self
        return (self
                .load_tos_ptr()
                .push(offset)
                .add()
                .store_tos_ptr()
                .inline_comment(f'TOS += {offset}'))

    def decr_tos(self, offset: Val) -> 'Unit':
        assert offset >= 0
        return (self
                .load_tos_ptr()
                .push(offset)
                .sub()
                .store_tos_ptr()
                .inline_comment(f'TOS -= {offset}'))

    def load_tos_ptr(self, offset: Val = 0) -> 'Unit':
        if offset == 0:
            return (self
                    .push(_TOS_ADDR_PTR)
                    .load())
        return (self
                .push(_TOS_ADDR_PTR)
                .load()
                .push(offset)
                .sub())

    def store_tos_ptr(self) -> 'Unit':
        return (self
                .push(_TOS_ADDR_PTR)
                .store())

    def load_tos(self, offset: Val = 0) -> 'Unit':
        return (self
                .load_tos_ptr(offset)
                .load()
                .inline_comment(f'Load TOS[{offset}]'))

    def store_tos(self, offset: Val = 0) -> 'Unit':
        return (self
                .load_tos_ptr(offset)
                .store()
                .inline_comment(f'Store TOS[{offset}]'))

    def push_tos(self) -> 'Unit':
        return (self
                .comment('push TOS {')
                .store_tos()
                .incr_tos(1)
                .comment('} push TOS'))

    def pop_tos(self) -> 'Unit':
        return (self
                .comment('pop TOS {')
                .decr_tos(1)
                .load_tos()
                .comment('} pop TOS'))

    @classmethod
    def fresh(cls) -> 'Unit':
        return (cls()
                .comment('entrypoint {')
                .push(_STACK_BASE)
                .push(_TOS_ADDR_PTR)
                .store()
                .call('main')
                .halt()
                .comment('} entrypoint'))

    def intrinsics(self) -> 'Unit':
        binary_ops = (
            ('add', Unit().add()),
            ('sub', Unit().sub()),
            # ('and', Unit().and_()),
            # ('or', Unit().or_()),
            # ('shr', Unit().shr()),
            ('shl', Unit().shl()),
        )
        for name, unit in binary_ops:
            (self
             .comment(f'def {name} {{')
             .label(name)
             .load_tos(1)
             .load_tos(0)
             .insert(unit)
             .rot()
             .ret()
             .comment(f'}} def {name}'))
        unary_ops = (
            ('print', Unit().print().push(0)),
        )
        for name, unit in unary_ops:
            (self
             .comment(f'def {name} {{')
             .label(name)
             .load_tos()
             .insert(unit)
             .rot()
             .ret()
             .comment(f'}} def {name}'))
        (self
         .comment('def exit {')
         .label('exit')
         .pop()  # Pop the return address
         .load_tos()
         .halt()
         .comment('} def exit'))
        (self
         .comment('def return {')
         .label('return')
         .load_tos()
         .rot()
         .pop()  # Pop the return address
         .rot()
         .ret()  # Return to the caller's return address
         .comment('} def return'))
        return self

    def __str__(self) -> str:
        lines = []
        for i, x in enumerate(self.instrs):
            if i in self.comments:
                lines.append(self.comments[i])
            line = (f'  {i:03} {x.kind.name:6} '
                    f'{(x.arg if x.arg is not None else ""):3}')
            if i in self.inline_comments:
                line += f'{"":6};' + self.inline_comments[i]
            lines.append(line)
        if i + 1 in self.comments:
            lines.append(self.comments[i + 1])
        return '\n'.join(lines)

    def to_program(self) -> Program:
        return self.instrs


def gen(stmt: Stmt) -> Unit:
    ns = Namespace()
    return (Unit()
            .fresh()
            .insert(gen_stmt(stmt, ns))
            .halt()
            .intrinsics()
            .link())


def gen_stmt(stmt: Stmt, ns: Namespace) -> Unit:
    child = stmt.child
    ns.push()
    if isinstance(child, Block):
        return gen_block(child, ns)
    elif isinstance(child, Expr):
        return gen_expr(child, ns).pop()
    elif isinstance(child, FnDef):
        return gen_fn_def(child, ns)
    elif isinstance(child, WhileLoop):
        return gen_while_loop(child, ns)
    elif isinstance(child, VarDecl):
        return gen_var_decl(child, ns)
    elif isinstance(child, Assign):
        return gen_assign(child, ns)
    else:
        raise NotImplementedError
    ns.pop()


def gen_block(block: Block, ns: Namespace) -> Unit:
    ns.push()
    units = [gen_stmt(child, ns) for child in block.children]
    ns.pop()
    return reduce(Unit.insert, units, Unit())


def gen_var_decl(var_decl: VarDecl, ns: Namespace) -> Unit:
    ns.pop()  # To inject the var into the parent's namespace
    ns.add([var_decl.name])
    ns.push()
    return Unit()


def gen_expr(expr: Expr, ns: Namespace) -> Unit:
    child = expr.child
    if isinstance(child, Lit):
        return gen_lit(child, ns)
    if isinstance(child, Var):
        return gen_var(child, ns)
    if isinstance(child, FnCall):
        return gen_fn_call(child, ns)
    else:
        raise NotImplementedError


def gen_fn_def(fn_def: FnDef, ns: Namespace) -> Unit:
    # The body of a function must leave the (single) return value on the
    # hardware stack.
    ns.push()
    ns.add(fn_def.arg_names)
    body = gen_stmt(fn_def.stmt, ns)
    ns.pop()
    return (Unit()
            .comment(f'def {fn_def.name} {{')
            .label(fn_def.name)
            .incr_tos(stack_size(fn_def))
            .insert(body)
            .decr_tos(stack_size(fn_def))
            .rot()
            .ret()
            .comment(f'}} def {fn_def.name}'))


def gen_while_loop(while_loop: WhileLoop, ns: Namespace) -> Unit:
    ns.push()
    guard = gen_expr(while_loop.guard, ns)
    ns.pop()
    ns.push()
    body = gen_stmt(while_loop.body, ns)
    ns.pop()
    start_label = Unit.new_label()
    guard_label = Unit.new_label()
    end_label = Unit.new_label()
    return (Unit()
            .comment('while loop {')
            .jmp(guard_label)
            .label(start_label)
            .comment('while body {')
            .insert(body)
            .comment('} while body')
            .comment('while guard {')
            .label(guard_label)
            .insert(guard)
            .jmp_t(start_label)
            .comment('} while guard')
            .label(end_label)
            .comment('} while loop'))


def gen_fn_call(fn_call: FnCall, ns: Namespace) -> Unit:
    ns.push()
    args_raw = [gen_expr(arg, ns) for arg in fn_call.args]
    ns.pop()
    args_pushed = [Unit().insert(arg).store_tos(i)
                   for i, arg in enumerate(args_raw)]
    args = reduce(Unit.insert, args_pushed,
                  Unit().comment(f'call {fn_call.name} {{'))
    return (args
            .call(fn_call.name)
            .inline_comment(fn_call.name)
            .comment(f'}} call {fn_call.name}'))


def gen_lit(lit: Lit, ns: Namespace) -> Unit:
    child = lit.child
    if isinstance(child, Int):
        return gen_int(child, ns)
    else:
        raise NotImplementedError


def gen_int(int_: Int, ns: Namespace) -> Unit:
    return Unit().push(int_.value).inline_comment(f'int {int_.value}')


def gen_assign(assign: Assign, ns: Namespace) -> Unit:
    ns.push()
    expr = gen_expr(assign.expr, ns)
    ns.pop()
    return (Unit()
            .insert(expr)
            .store_tos(ns.get(assign.name))
            .inline_comment(assign.name))


def gen_var(var: Var, ns: Namespace) -> Unit:
    return Unit().load_tos(ns.get(var.name)).inline_comment(var.name)


@singledispatch
def stack_size(node: Node) -> int:
    return 0

@stack_size.register
def _stack_size_stmt(node: Stmt) -> int:
    return stack_size(node.child)

@stack_size.register
def _stack_size_block(node: Block) -> int:
    static = 0
    biggest_block = 0
    for child in node.children:
        stmt = child.child
        if isinstance(stmt, [Block, WhileLoop]):
            block_size = stack_size(stmt)
            if block_size > biggest_block:
                biggest_block = block_size
        else:
            static += stack_size(stmt)
    return static + biggest_block

@stack_size.register
def _stack_size_fn_def(node: FnDef) -> int:
    return len(node.arg_names) + stack_size(node.stmt)

@stack_size.register
def _stack_size_while_loop(node: WhileLoop) -> int:
    return stack_size(node.guard) + stack_size(node.body)

@stack_size.register
def _stack_size_var_decl(node: VarDecl) -> int:
    return 1

@stack_size.register
def _stack_size_expr(node: Expr) -> int:
    return 0

@stack_size.register
def _stack_size_var(node: Var) -> int:
    return 0

@stack_size.register
def _stack_size_fn_call(node: FnCall) -> int:
    return 0

@stack_size.register
def _stack_size_lit(node: Lit) -> int:
    return 0

@stack_size.register
def _stack_size_int(node: Int) -> int:
    return 0

@stack_size.register
def _stack_size_assign(node: Assign) -> int:
    return 0
