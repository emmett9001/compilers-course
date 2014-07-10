# gonellvm.py
'''
Project 5 : Generate LLVM
=========================
In this project, you're going to translate the SSA intermediate code
into LLVM IR.    Once you're done, your code will be runnable.  It
is strongly advised that you do *all* of the steps of Exercise 5
prior to starting this project.   Don't rush into it.

The basic idea of this project is exactly the same as the interpreter
in Project 4.   You'll make a class that walks through the instruction
sequence and triggers a method for each kind of instruction.  Instead
of running the instruction however, you'll be generating LLVM
instructions.

Further instructions are contained in the comments.
'''

# LLVM imports. Don't change this.
from llvm.core import Module, Builder, Function, Type, Constant, GlobalVariable
from llvm.core import (
    FCMP_UEQ, FCMP_UGE, FCMP_UGT, FCMP_ULE, FCMP_ULT, FCMP_UNE,
    ICMP_EQ, ICMP_NE, ICMP_SGE, ICMP_SGT, ICMP_SLE, ICMP_SLT
)
from goneblock import BaseLLVMBlockVisitor, Block

# Declare the LLVM type objects that you want to use for the types
# in our intermediate code.  Basically, you're going to need to
# declare your integer, float, and string types here.

int_type = Type.int()         # 32-bit integer
float_type = Type.double()      # 64-bit float
string_type = None               # Up to you (leave until the end)
bool_type = Type.int(1)               # Up to you (leave until the end)

# A dictionary that maps the typenames used in IR to the corresponding
# LLVM types defined above.   This is mainly provided for convenience
# so you can quickly look up the type object given its type name.
typemap = {
    'int': int_type,
    'float': float_type,
    'string': string_type,
    'bool': bool_type
}

# The following class is going to generate the LLVM instruction stream.
# The basic features of this class are going to mirror the experiments
# you tried in Exercise 5.  The execution module is very similar
# to the interpreter written in Project 4.  See specific comments
# in the class.


class GenerateLLVMBlockVisitor(BaseLLVMBlockVisitor):
    def __init__(self):
        super(GenerateLLVMBlockVisitor, self).__init__()
        self.inner_block_visitor = None
        self.vars = {}
        self.temps = {}
        self.module = Module.new("module")
        self.function = Function.new(self.module,
                                     Type.function(Type.void(), [], False),
                                     "main")
        block = self.function.append_basic_block('entry')
        self.start_block = block
        self.builder = Builder.new(block)
        self.declare_runtime_library()

    def declare_runtime_library(self):
        self.runtime = {}

        self.runtime['_print_int'] = Function.new(self.module,
                                                  Type.function(Type.void(), [int_type], False),
                                                  "_print_int")
        self.runtime['_print_float'] = Function.new(self.module,
                                                    Type.function(Type.void(), [float_type], False),
                                                    "_print_float")
        self.runtime['_print_bool'] = Function.new(self.module,
                                                   Type.function(Type.void(), [bool_type], False),
                                                   "_print_bool")

    def visit(self, block):
        while isinstance(block, Block):
            name = "visit_%s" % type(block).__name__
            if hasattr(self, name) and block not in self.visited_blocks:
                getattr(self, name)(block)
                self.visited_blocks |= {block}
            block = block.next_block

    def visit_BasicBlock(self, block, pred=None):
        self.inner_block_visitor.generate_code(block)

    def visit_ConditionalBlock(self, block):
        self.visit_BasicBlock(block)

        then_block = self.inner_block_visitor.add_block("then")
        else_block = self.inner_block_visitor.add_block("else")
        merge_block = self.inner_block_visitor.add_block("merge")

        self.inner_block_visitor.cbranch(block.testvar, then_block, else_block)

        self.inner_block_visitor.set_block(then_block)
        self.visit(block.true_branch)
        self.inner_block_visitor.branch(merge_block)

        self.inner_block_visitor.set_block(else_block)
        self.visit(block.false_branch)
        self.inner_block_visitor.branch(merge_block)

        self.inner_block_visitor.set_block(merge_block)

    def visit_WhileBlock(self, block):
        test_block = self.inner_block_visitor.add_block("whiletest")

        self.inner_block_visitor.branch(test_block)
        self.inner_block_visitor.set_block(test_block)

        self.inner_block_visitor.generate_code(block)

        loop_block = self.inner_block_visitor.add_block("loop")
        after_loop = self.inner_block_visitor.add_block("afterloop")

        self.inner_block_visitor.cbranch(block.testvar, loop_block, after_loop)

        self.inner_block_visitor.set_block(loop_block)
        self.visit(block.loop_branch)
        self.inner_block_visitor.branch(test_block)

        self.inner_block_visitor.set_block(after_loop)

    def return_void(self):
        self.builder.ret_void()


class GenerateLLVM(object):
    def __init__(self, blockvisitor=None):
        self.blockvisitor = blockvisitor

    @property
    def vars(self):
        return self.blockvisitor.vars

    @property
    def temps(self):
        return self.blockvisitor.temps

    @property
    def builder(self):
        return self.blockvisitor.builder

    @property
    def module(self):
        return self.blockvisitor.module

    @property
    def runtime(self):
        return self.blockvisitor.runtime

    @property
    def function(self):
        return self.blockvisitor.function

    def set_block(self, block):
        self.builder.position_at_end(block)

    def add_block(self, name):
        return self.function.append_basic_block(name)

    def cbranch(self, testvar, true_block, false_block):
        self.builder.cbranch(self.temps[testvar], true_block, false_block)

    def branch(self, next_block):
        self.builder.branch(next_block)

    def generate_code(self, block):
        for op in block.instructions:
            opcode = op[0]
            if hasattr(self, "emit_" + opcode):
                getattr(self, "emit_" + opcode)(*op[1:])
            else:
                print("Warning: No emit_" + opcode + "() method")

    # Creation of literal values.  Simply define as LLVM constants.
    def emit_literal_int(self, value, target):
        self.temps[target] = Constant.int(int_type, value)

    def emit_literal_float(self, value, target):
        self.temps[target] = Constant.real(float_type, value)

    def emit_literal_bool(self, value, target):
        self.temps[target] = Constant.int(bool_type, 1 if value else 0)

    # Allocation of variables.  Declare as global variables and set to
    # a sensible initial value.
    def emit_alloc_int(self, name):
        var = GlobalVariable.new(self.module, int_type, name)
        var.initializer = Constant.int(int_type, 0)
        self.vars[name] = var

    def emit_alloc_float(self, name):
        var = GlobalVariable.new(self.module, float_type, name)
        var.initializer = Constant.real(float_type, 0.0)
        self.vars[name] = var

    def emit_alloc_bool(self, name):
        var = GlobalVariable.new(self.module, bool_type, name)
        var.initializer = Constant.int(bool_type, 0)
        self.vars[name] = var

    # Load/store instructions for variables.  Load needs to pull a
    # value from a global variable and store in a temporary. Store
    # goes in the opposite direction.
    def emit_load_int(self, name, target):
        self.temps[target] = self.builder.load(self.vars[name], target)

    def emit_load_float(self, name, target):
        self.temps[target] = self.builder.load(self.vars[name], target)

    def emit_load_bool(self, name, target):
        self.temps[target] = self.builder.load(self.vars[name], target)

    def emit_store_int(self, source, target):
        self.builder.store(self.temps[source], self.vars[target])

    def emit_store_float(self, source, target):
        self.builder.store(self.temps[source], self.vars[target])

    def emit_store_bool(self, source, target):
        self.builder.store(self.temps[source], self.vars[target])

    # Binary + operator
    def emit_add_int(self, left, right, target):
        self.temps[target] = self.builder.add(self.temps[left], self.temps[right], target)

    def emit_add_float(self, left, right, target):
        self.temps[target] = self.builder.fadd(self.temps[left], self.temps[right], target)

    # Binary - operator
    def emit_sub_int(self, left, right, target):
        self.temps[target] = self.builder.sub(self.temps[left], self.temps[right], target)

    def emit_sub_float(self, left, right, target):
        self.temps[target] = self.builder.fsub(self.temps[left], self.temps[right], target)

    # Binary * operator
    def emit_mul_int(self, left, right, target):
        self.temps[target] = self.builder.mul(self.temps[left], self.temps[right], target)

    def emit_mul_float(self, left, right, target):
        self.temps[target] = self.builder.fmul(self.temps[left], self.temps[right], target)

    # Binary / operator
    def emit_div_int(self, left, right, target):
        self.temps[target] = self.builder.sdiv(self.temps[left], self.temps[right], target)

    def emit_div_float(self, left, right, target):
        self.temps[target] = self.builder.fdiv(self.temps[left], self.temps[right], target)

    def emit_lt_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_SLT, self.temps[left], self.temps[right], target)

    def emit_gt_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_SGT, self.temps[left], self.temps[right], target)

    def emit_lte_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_SLE, self.temps[left], self.temps[right], target)

    def emit_gte_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_SGE, self.temps[left], self.temps[right], target)

    def emit_eq_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_EQ, self.temps[left], self.temps[right], target)

    def emit_neq_int(self, left, right, target):
        self.temps[target] = self.builder.icmp(ICMP_NE, self.temps[left], self.temps[right], target)

    def emit_lt_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_ULT, self.temps[left], self.temps[right], target)

    def emit_gt_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_UGT, self.temps[left], self.temps[right], target)

    def emit_lte_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_ULE, self.temps[left], self.temps[right], target)

    def emit_gte_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_UGE, self.temps[left], self.temps[right], target)

    def emit_eq_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_UEQ, self.temps[left], self.temps[right], target)

    def emit_neq_float(self, left, right, target):
        self.temps[target] = self.builder.icmp(FCMP_UNE, self.temps[left], self.temps[right], target)

    def emit_and_bool(self, left, right, target):
        self.temps[target] = self.builder.and_(self.temps[left], self.temps[right], target)

    def emit_or_bool(self, left, right, target):
        self.temps[target] = self.builder.or_(self.temps[left], self.temps[right], target)

    def emit_not_bool(self, source, target):
        self.temps[target] = self.builder.not_(self.temps[source])

    # Unary + operator
    def emit_uadd_int(self, source, target):
        self.temps[target] = self.builder.add(
            Constant.int(int_type, 0),
            self.temps[source],
            target)

    def emit_uadd_float(self, source, target):
        self.temps[target] = self.builder.fadd(
            Constant.real(float_type, 0.0),
            self.temps[source],
            target)

    # Unary - operator
    def emit_usub_int(self, source, target):
        self.temps[target] = self.builder.mul(
            Constant.int(int_type, -1),
            self.temps[source],
            target)

    def emit_usub_float(self, source, target):
        self.temps[target] = self.builder.fmul(
            Constant.real(float_type, -1.0),
            self.temps[source],
            target)

    # Print statements
    def emit_print_int(self, source):
        self.builder.call(self.runtime['_print_int'], [self.temps[source]])

    def emit_print_float(self, source):
        self.builder.call(self.runtime['_print_float'], [self.temps[source]])

    def emit_print_bool(self, source):
        self.builder.call(self.runtime['_print_bool'], [self.temps[source]])

    # Extern function declaration.
    def emit_extern_func(self, name, rettypename, *parmtypenames):
        rettype = typemap[rettypename]
        parmtypes = [typemap[pname] for pname in parmtypenames]
        func_type = Type.function(rettype, parmtypes, False)
        self.vars[name] = Function.new(self.module, func_type, name)

    # Call an external function.
    def emit_call_func(self, funcname, target, *funcargs):
        resolved_args = []
        for arg in funcargs:
            resolved_args.append(self.temps[arg])
        self.temps[target] = self.builder.call(self.vars[funcname], resolved_args)


def main():
    import gonelex
    import goneparse
    import gonecheck
    import gonecode
    import sys
    import ctypes
    import time
    from errors import subscribe_errors, errors_reported
    from llvm.ee import ExecutionEngine

    # Load the Gone runtime library (see Makefile)
    ctypes._dlopen('./gonert.so', ctypes.RTLD_GLOBAL)

    lexer = gonelex.make_lexer()
    parser = goneparse.make_parser()
    with subscribe_errors(lambda msg: sys.stdout.write(msg + "\n")):
        program = parser.parse(open(sys.argv[1]).read())
        # Check the program
        gonecheck.check_program(program)
        # If no errors occurred, generate code
        if not errors_reported():
            code = gonecode.generate_code(program)
            # Emit the code sequence
            g = GenerateLLVMBlockVisitor()
            inner_block_visitor = GenerateLLVM(blockvisitor=g)
            g.inner_block_visitor = inner_block_visitor
            g.visit(code.start_block)
            g.return_void()
            #print(g.module)

            # Verify and run function that was created during code generation
            print(":::: RUNNING ::::")
            g.function.verify()
            llvm_executor = ExecutionEngine.new(g.module)
            start = time.clock()
            llvm_executor.run_function(g.function, [])
            print(":::: FINISHED ::::")
            print("execution time: {0:.15f}s".format(time.clock() - start))

if __name__ == '__main__':
    main()
