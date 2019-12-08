from andes.core.var import Algeb, State
from typing import Optional
from andes.core.discrete import HardLimiter


class Block(object):
    r"""
    Base class for control blocks.

    Blocks are meant to be instantiated as Model attributes to provide pre-defined equation sets. Subclasses
    must overload the `__init__` method to take custom inputs.
    Subclasses of Block must overload the `define` method to provide initialization and equation strings.
    Exported variables, services and blocks must be constructed into a dictionary ``self.vars`` at the end of
    the constructor.

    Blocks can be nested. A block can have blocks but itself as attributes and therefore reuse equations. When a
    block has sub-blocks, the outer block must be constructed with a``name``.

    Nested block works in the following way: the parent block modifies the sub-block's ``name`` attribute by
    prepending the parent block's name at the construction phase. The parent block then exports the sub-block
    as a whole. When the parent Model class picks up the block, it will recursively import the variables in the
    block and the sub-blocks correctly. See the example section for details.

    Parameters
    ----------
    name : str, optional
        Block name
    tex_name : str, optional
        Block LaTeX name
    info : str, optional
        Block description.

    Warnings
    --------
    It is suggested to have at most one level of nesting to avoid messy variable names.

    Examples
    --------
    Example for two-level nested blocks. Suppose we have the following hierarchy ::

        SomeModel  instance M
           |
        LeadLag A  exports (x, y)
           |
        Lag B      exports (x, y)

    SomeModel instance M contains an instance of Leadlag block named A, which contains an instance of a Lag block
    named B. Both A and B exports two variables ``x`` and ``y``.

    In the code of Model, the following code is used to instantiate LeadLag ::

        class SomeModel:
            def __init__(...)
                ...
                self.A = LeadLag(name='A', u=self.foo1, T1=self.foo2, T2=self.foo3)

    To use Lag in the LeadLag code, the following lines are found in the constructor of LeadLag ::

        class LeadLag:
            def __init__(name, ...)
                ...
                self.B = Lag(u=self.y, K=self.K, T=self.T)
                self.vars = {..., 'A': self.A}

    The ``__setattr__`` magic of LeadLag takes over the construction and assigns ``B.name`` as ``A_B``,
    given A's name provided at run time. ``self.A`` is exported with the internal name ``A`` at the end.

    Again, the LeadLag instance name (``A`` in this example) MUST be provided in SomeModel's constructor for the
    name prepending to work correctly. If there is more than one level of nesting, other than the leaf-level
    block, all parent blocks' names must be provided at instantiation.

    When A is picked up by ``SomeModel.__setattr__``, B is captured from A's exports. Recursively, B's variables
    are exported, Recall that ``B.name`` is ``A_B``, following the naming rule (parent block's name + variable
    name), B's internal variables become ``A_B_x`` and ``A_B_y``.

    In this way, B's ``define`` needs mo modification since the naming rule is the same. For example,
    B's internal y is always ``{self.name}_y``, although B has gotten a new name ``A_B``.

    """

    def __init__(self, name: Optional[str] = None, tex_name: Optional[str] = None, info: Optional[str] = None):
        self.name = name
        self.tex_name = tex_name if tex_name else name
        self.info = info
        self.owner = None
        self.vars = {}

        self.ifx, self.jfx, self.vfx = list(), list(), list()
        self.ify, self.jfy, self.vfy = list(), list(), list()
        self.igx, self.jgx, self.vgx = list(), list(), list()
        self.igy, self.jgy, self.vgy = list(), list(), list()
        self.itx, self.jtx, self.vtx = list(), list(), list()
        self.irx, self.jrx, self.vrx = list(), list(), list()

        self.ifxc, self.jfxc, self.vfxc = list(), list(), list()
        self.ifyc, self.jfyc, self.vfyc = list(), list(), list()
        self.igxc, self.jgxc, self.vgxc = list(), list(), list()
        self.igyc, self.jgyc, self.vgyc = list(), list(), list()
        self.itxc, self.jtxc, self.vtxc = list(), list(), list()
        self.irxc, self.jrxc, self.vrxc = list(), list(), list()

    def __setattr__(self, key, value):
        # handle sub-blocks by prepending self.name
        if isinstance(value, Block):
            if self.name is None:
                raise ValueError(f"`name` must be specified when constructing {self.class_name} instances.")
            if not value.owner:
                value.__dict__['owner'] = self

            if not value.name:
                value.__dict__['name'] = self.name + '_' + key
            else:
                value.__dict__['name'] = self.name + '_' + value.name

            if not value.tex_name:
                value.__dict__['tex_name'] = self.name + r'\ ' + key
            else:
                value.__dict__['tex_name'] = self.name + r'\ ' + value.tex_name

        self.__dict__[key] = value

    def j_reset(self):
        """
        Helper function to clear the lists holding the numerical jacobians
        """
        self.ifx, self.jfx, self.vfx = list(), list(), list()
        self.ify, self.jfy, self.vfy = list(), list(), list()
        self.igx, self.jgx, self.vgx = list(), list(), list()
        self.igy, self.jgy, self.vgy = list(), list(), list()

        self.ifxc, self.jfxc, self.vfxc = list(), list(), list()
        self.ifyc, self.jfyc, self.vfyc = list(), list(), list()
        self.igxc, self.jgxc, self.vgxc = list(), list(), list()
        self.igyc, self.jgyc, self.vgyc = list(), list(), list()

    def define(self):
        """
        Function for setting the initialization and equation strings for internal variables. This method must be
        implemented by subclasses.

        The equations should be written with the "final" variable names.
        Let's say the block instance is named `blk` (kept at ``self.name`` of the block), and an internal
        variable `v` is defined.
        The internal variable will be captured as ``blk_v`` by the owner model. Therefore, all equations should
        use ``{self.name}_v`` to represent variable ``v``, where ``{self.name}`` is the name of the block at
        run time.

        On the other hand, the names of externally provided parameters or variables are obtained by
        directly accessing the ``name`` attribute. For example, if ``self.T`` is a parameter provided through
        the block constructor, ``{self.T.name}`` should be used in the equation.

        Examples
        --------
        An internal variable ``v`` has a trivial equation ``T = v``, where T is a parameter provided to the block
        constructor.

        In the model, one has ::

            class SomeModel():
                def __init__(...)
                    self.input = Algeb()
                    self.T = Param()

                    self.blk = ExampleBlock(u=self.input, T=self.T)

        In the ExampleBlock function, the internal variable is defined in the constructor as ::

            class ExampleBlock():
                def __init__(...):
                    self.v = Algeb()
                    self.vars = {'v', self.v}

        In the ``define``, the equation is provided as ::

            def define(self):
                self.v.v_init = '{self.T.name}'
                self.v.e_str = '{self.T.name} - {self.name}_v'

        In the owner model, ``v`` from the block will be captured as ``blk_v``, and the equation will become ::

            self.blk_v.v_init = 'T'
            self.blk_v.e_str = 'T - blk_v'

        See Also
        --------
        PIController.define : Equations for the PI Controller block

        """
        raise NotImplementedError(f'define() method not implemented in {self.class_name}')

    def export(self):
        """
        Method for exporting instances defined in this class in a dictionary. This method calls the ``define``
        method first and returns ``self.vars``.

        Returns
        -------
        dict
            Keys are the (last section of the) variable name, and the values are the attribute instance.
        """
        self.define()
        return self.vars

    def g_numeric(self, **kwargs):
        """
        Function to customize function calls
        """
        pass

    def f_numeric(self, **kwargs):
        """
        Function to customize differential function calls
        """
        pass

    def c_numeric(self, **kwargs):
        pass

    def j_numeric(self):
        """
        This function stores the constant and variable jacobian information.

        Constant jacobians are stored by indices and values in `ifxc`, `jfxc`
        and `vfxc`. Note that it is the values that gets stored in `vfxc`.
        Variable jacobians are stored by indices and functions. The function
        shall return the value of the corresponding jacobian elements.

        """
        pass

    @property
    def class_name(self):
        """Return the class name"""
        return self.__class__.__name__


class SampleAndHolder(Block):
    """
    Sample and hold block

    Warnings
    --------
    Not implemented yet.
    """
    pass


class PIController(Block):
    """
    Proportional Integral Controller with the reference from an external variable

    Parameters
    ----------
    u : VarBase
        The input variable instance
    ref : Union[VarBase, ParamBase]
        The reference instance
    kp : ParamBase
        The proportional gain parameter instance
    ki : [type]
        The integral gain parameter instance

    """
    def __init__(self, u, ref, kp, ki, name=None, info=None):
        super(PIController, self).__init__(name=name, info=info)

        self.u = u
        self.ref = ref
        self.kp = kp
        self.ki = ki

        self.xi = State(info="Integration value of PI controller")
        self.y = Algeb(info="Integration value of PI controller")

        self.vars = {'xi': self.xi, 'y': self.y}

    def define(self):
        r"""
        Define equations for the PI Controller.

        Notes
        -----
        One state variable ``xi`` and one algebraic variable ``y`` are added.

        Equations implemented are

        .. math ::
            \dot{x_i} = k_i * (ref - var)

            y = x_i + k_i * (ref - var)
        """

        self.xi.e_str = f'ki * ({self.ref.name} - {self.u.name})'
        self.y.e_str = f'kp * ({self.ref.name} - {self.u.name}) + {self.name}_xi'


class PIControllerNumeric(Block):

    def __init__(self, u, ref, kp, ki, name=None, info=None):
        super().__init__(name=name, info=info)

        self.u = u
        self.ref = ref
        self.kp = kp
        self.ki = ki

        self.xi = State(info="Integration value of PI controller")
        self.y = Algeb(info="Integration value of PI controller")

        self.vars = {'xi': self.xi, 'y': self.y}

    def g_numeric(self, **kwargs):
        self.y.e = self.kp.v * (self.ref.v - self.u.v) + self.xi.v

    def f_numeric(self, **kwargs):
        self.xi.e = self.ki.v * (self.ref.v - self.u.v)

    def store_jacobian(self):
        self.j_reset()

        self.ifyc.append(self.xi.a)
        self.jfyc.append(self.u.a)
        self.vfyc.append(-self.ki.v)

        self.igyc.append(self.y.a)
        self.jgyc.append(self.u.v)
        self.vgyc.append(-self.kp.v)

        self.igxc.append(self.y.a)
        self.jgxc.append(self.xi.a)
        self.vgxc.append(1)

    def define(self):
        """Skip the symbolic definition"""
        pass


class Washout(Block):
    r"""
    Washout filter (high pass) block ::

                sT1
         u -> ------- -> y
              1 + sT2

    """

    def __init__(self, u, T, info=None, name=None):
        super().__init__(name=name, info=info)
        self.T = T
        self.u = u

        self.x = State(info='State in washout filter', tex_name="x'")
        self.y = Algeb(info='Output of washout filter', tex_name=r'y')
        self.vars = {'x': self.x, 'y': self.y}

    def define(self):
        r"""
        Notes
        -----
        Equations and initial values:

        .. math ::
            \dot{x'} = (u - x) / T \\
            y = u - x \\
            x'_0 = u \\
            y_0 = 0

        """
        self.x.v_init = f'{self.u.name}'
        self.y.v_init = f'0'

        self.x.e_str = f'({self.u.name} - {self.name}_x) / {self.T.name}'
        self.y.e_str = f'({self.u.name} - {self.name}_x) - {self.name}_y'


class Lag(Block):
    r"""
    Lag (low pass) transfer function block ::

                K
        u -> ------ -> y
             1 + sT

    Exports one state variable `x` as the output.

    Parameters
    ----------
    K
        Gain
    T
        Time constant
    u
        Input variable

    """
    def __init__(self, u, K, T, name=None, info='Lag transfer function'):
        super().__init__(name=name, info=info)

        self.K = K
        self.T = T
        self.u = u
        self.x = State(info='State in lag transfer function', tex_name="x'")

        self.vars = {'x': self.x}

    def define(self):
        r"""

        Notes
        -----
        Equation and initial value

        .. math ::

            \dot{x'} = (u - x) / T
            x'_0 = u

        """
        self.x.v_init = f'{self.u.name}'
        self.x.e_str = f'({self.K.name} * {self.u.name} - {self.name}_x) / {self.T.name}'


class LeadLag(Block):
    r"""
    Lead-Lag transfer function block in series implementation ::

             1 + sT1
        u -> ------- -> y
             1 + sT2

    Exports two variables: state x and output y.

    Parameters
    ----------
    T1
        Time constant 1
    T2
        Time constant 2


    """
    def __init__(self, u, T1, T2, name=None, info='Lead-lag transfer function'):
        super().__init__(name=name, info=info)
        self.T1 = T1
        self.T2 = T2
        self.u = u

        self.x = State(info='State in lead-lag transfer function', tex_name="x'")
        self.y = Algeb(info='Output of lead-lag transfer function', tex_name=r'y')
        self.vars = {'x': self.x, 'y': self.y}

    def define(self):
        r"""

        Notes
        -----

        Implemented equations and initial values

        .. math ::

            \dot{x'} = (u - x') / T_2 \\
            y = \frac {T_1} {T_2} * (u - x') + x' \\
            x'_0 = y_0 = u

        """
        self.x.v_init = f'{self.u.name}'
        self.y.v_init = f'{self.u.name}'

        self.x.e_str = f'({self.u.name} - {self.name}_x) / {self.T2.name}'
        self.y.e_str = f'{self.T1.name} / {self.T2.name} * ({self.u.name} - {self.name}_x) + \
                         {self.name}_x - \
                         {self.name}_y'


class LeadLagLimit(Block):
    r"""
    Lead-Lag transfer function block with hard limiter (series implementation) ::

                       ___upper___
                      /
                  1 + sT1
           u ->   -------  -> y
                  1 + sT2
        __lower____/

    Exports four variables: state `x`, output before hard limiter `ynl`, output `y`, and limiter `lim`,

    """
    def __init__(self, u, T1, T2, lower, upper, name=None, info='Lead-lag transfer function'):
        super().__init__(name=name, info=info)
        self.T1 = T1
        self.T2 = T2
        self.u = u
        self.lower = lower
        self.upper = upper

        self.x = State(info='State in lead-lag transfer function', tex_name="x'")
        self.ynl = Algeb(info='Output of lead-lag transfer function before limiter', tex_name=r'y_{nl}')
        self.y = Algeb(info='Output of lead-lag transfer function after limiter', tex_name=r'y')
        self.lim = HardLimiter(u=self.y, lower=self.lower, upper=self.upper)

        self.vars = {'x': self.x, 'ynl': self.ynl, 'y': self.y, 'lim': self.lim}

    def define(self):
        r"""

        Notes
        -----

        Implemented equations and initial values

        .. math ::

            \dot{x'} = (u - x') / T_2 \\
            y = \frac {T_1} {T_2} * (u - x') + x' \\
            x'_0 = y_0 = u

        """
        self.x.v_init = f'{self.u.name}'
        self.ynl.v_init = f'{self.u.name}'
        self.y.v_init = f'{self.u.name}'

        self.x.e_str = f'({self.u.name} - {self.name}_x) / {self.T2.name}'
        self.ynl.e_str = f'{self.T1.name} / {self.T2.name} * ({self.u.name} - {self.name}_x) + ' \
                         f'{self.name}_x - ' \
                         f'{self.name}_ynl'

        self.y.e_str = f'{self.name}_ynl * {self.name}_lim_zi + ' \
                       f'{self.lower.name} * {self.name}_lim_zl + ' \
                       f'{self.upper.name} * {self.name}_lim_zu - ' \
                       f'{self.name}_y'