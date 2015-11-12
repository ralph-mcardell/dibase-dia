'''
Python Dia export plug-in script.
[Developed using Python 2.7]
Next Code Gen(eration) on diagram export.
An attempt at a cleaner expression of producing and consuming a diagram's
code generation internal representation.

Currently only writes class diagrams as skeleton Python source.
Enhances Python produced by the provided codegen.py plug-in by taking note of
a class's defined __init__ method and, if defined creating an __init__
method for the generated class matching the signature of the one in the
diagram. Further, if a provided __init__ method has parameters whose names
match that of class instance attribute then these are used to initialise the
class instance attribute of the same name, thus a class with an instance
attribute 'attrib' and a __init__ method taking a parameter named 'attrib'
will produce a line:
  self.attrib = attrib
in the written __init__ method's definition.
'''

import sys, dia

class NCGenConfig:
  '''
  Module global configuration values - change to customise.
  TODO: find some way to set these other than editing this file.
  '''
  indent = "  "

def ConditionallyPrefix(prefix, value):
  ''' Prefix a string with another only if it is not empty '''
  return ''.join([prefix,value]) if value else ''

class AttributeRepr:
  '''
  Internal representation of a class attribute
  '''
  def __init__(self, attrib):
    '''
    Initialise instance attributes from the attrib parameter,
    a Dia class attribute value list
    '''
    self.__name = attrib[0]
    self.__type = attrib[1]
    self.__value = attrib[2]
    self.__comment = attrib[3]
    self.__visibility = attrib[4]
    self.__isAbstract = attrib[5]
    self.__hasClassScope = attrib[6]
  def Name(self):
    return self.__name
  def Type(self):
    return self.__type
  def Value(self):
    return self.__value
  def Comment(self):
    return self.__comment
  def Visibility(self):
    return self.__visibility
  def IsAbstract(self):
    return self.__isAbstract
  def HasClassScope(self):
    return self.__hasClassScope

class ParameterRepr:
  '''
  Internal representation of a class operation parameter
  '''
  def __init__(self, param):
    '''
    Initialise instance attributes from the param parameter,
    a Dia class parameter value list
    '''
    self.__name = param[0]
    self.__type = param[1]
    self.__value = param[2]
    self.__comment = param[3]
    self.__kind = param[4]
  def Name(self):
    return self.__name
  def Type(self):
    return self.__type
  def Value(self):
    return self.__value
  def Comment(self):
    return self.__comment
  def Kind(self):
    return self.__kind

class OperationRepr:
  '''
  Internal representation of a class operation (method, member function etc.)
  '''
  def __init__(self, op):
    '''
    Initialise instance attributes from the op parameter,
    a Dia class operation value list
    '''
    self.__name = op[0]
    self.__type = op[1]
    self.__comment = op[2]
    self.__stereotype = op[3]
    self.__visibility = op[4]
    self.__isAbstract = op[5]
    self.__isQuery = op[6] # C++ const method
    self.__hasClassScope = op[7]
    self.__parameters = []
    for p in op[8]:
      self.__parameters.append(ParameterRepr(p))
  def Name(self):
    return self.__name
  def Type(self):
    return self.__type
  def Comment(self):
    return self.__comment
  def Stereotype(self):
    return self.__stereotype
  def Visibility(self):
    return self.__visibility
  def IsQuery(self):
    return self.__isQuery
  def IsAbstract(self):
    return self.__isAbstract
  def HasClassScope(self):
    return self.__hasClassScope
  def Parameters(self):
    return self.__parameters

class ClassRepr:
  '''
  Internal representation of a class
  TODO: Add support for class templates and class realisations
        from templates
  '''
  def __init__(self, classObject):
    '''
    Initialise instance attributes from the classObject parameter,
    a Dia class object
    '''
    props = classObject.properties
    self.__name = props["name"].value
    self.__comment = props["comment"].value
    self.__isAbstract = props["abstract"].value
    self.__isTemplate = props["template"].value
    self.__attributes = {}
    for a in props["attributes"].value:
      self.__attributes[a[0]] = AttributeRepr(a)
    self.__operations = {}
    for o in props["operations"].value:
      opName = o[0]
      if opName not in self.__operations:
        self.__operations[opName] = [] # use map of lists as op.  names can be overloaded
      self.__operations[opName].append(OperationRepr(o))
    self.__supers = []
    self.__subs = []
    for c in classObject.connections:
      self.__ProcessConnection(c)
  def Name(self):
    return self.__name
  def Comment(self):
    return self.__comment
  def IsAbstract(self):
    return self.__isAbstract
  def IsTemplate(self):
    return self.__isTemplate
  def Attributes(self):
    return self.__attributes
  def Operations(self):
    return self.__operations
  def Superclasses(self):
    return self.__supers
  def Subclasses(self):
    return self.__subs
  def __ProcessConnection(self, conn):
    for node in conn.connected:
      if node.type.name == "UML - Generalization":
        self.__ProcessGeneralisation(node)
  def __ProcessGeneralisation(self, node):
    parent = node.handles[0].connected_to
    child = node.handles[1].connected_to
    if parent and child:
      superclass = parent.object.properties["name"].value
      subclass = child.object.properties["name"].value
      if subclass==self.__name: # if we are the subclass...
        self.__supers.append(superclass)
      elif superclass==self.__name: # if we are the superclass...
        self.__subs.append(subclass)
      else:
        raise AssertionError("Diagram UML Class object has generalisation "
                             "for which it is neither the superclass ('%s') "
                             "nor the subclass ('%s')."%(superclass,subclass))

class ClassDiagRepr:
  '''
  Class diagram representation type.
  Provides support for adding classes to the representation from a
  Dia-provided class object and accessing the resultant internal
  ClassRepr using subscript by name notation:
    cdr[clsName] = diaClassObject
    internalClassRepr = cdr[className]

  ClassDiagRepr is also an iterable type, providing an iterator that
  ensures the order of the ClassRepr objects returned represents classes
  in a base to derived ordering that is valid in so much as languages
  generally require all a class's base classes to have been defined
  before it is.
  '''
  class __Node:
    __indent = 0
    def __init__(self, classObject):
      self.clsRepr = ClassRepr(classObject)
      self.depth = -999 # ridiculously low initial derivation depth
    def Name(self):
      return self.clsRepr.Name()
    def Subs(self):
      return self.clsRepr.Subclasses()
    def Supers(self):
      return self.clsRepr.Superclasses()
    def ConditionallySetDepth(self, newDepth, nodes):
      if newDepth > self.depth:
        self.depth = newDepth
        for subName in self.Subs():
          if subName in nodes:
            nodes[subName].ConditionallySetDepth(newDepth+1,nodes)

  class __Iterator:
    ''' Returns diagram classes in declaration-valid order '''
    def __init__(self, classDiagRepr):
      self.__cdr = classDiagRepr
      self.__nodepos = iter(classDiagRepr.sorted)
    def next(self):
      while True:
        try:
          name = self.__nodepos.next()
          return self.__cdr[name] 
        except StopIteration:
          raise

  def __init__(self):
    '''
    Initialise class collections.
    Classes are represented as internal nodes containing a ClassRepr plus
    additional housekeeping data. The nodes are stored in two collections:
    - a dictionary keyed by class name that forms the direct access view
    - a sorted list of classes used when iterating over the class nodes
      in base before derived order.
    '''
    self.classes = {}
    self.sorted = None
  def __getitem__(self, name):
    '''
    Return the ClassRepr object associated with the passed class name.
    '''
    return self.classes[name].clsRepr
  def __setitem__(self,name,value):
    '''
    Add a class representation node to a ClassDiagRepr object.
    Note: derivation depth information for the node is calculated
    for use in producing a sorted by derivation list of nodes that
    can be iterated over.
    '''
    self.sorted = None # adding class invalidates ordering
    node = ClassDiagRepr.__Node(value)
    node.ConditionallySetDepth(self.__determineClassDerivationDepth(node), self.classes)
    self.classes[name] = node
  def __iter__(self):
    '''
    Return an instance of the internal iterator type ensuring the required
    derivation depth sorted sequence of class representation nodes is produced.
    '''
    if not self.sorted:
      self.sorted = sorted(self.classes, key=lambda name: self.classes[name].depth)
    return ClassDiagRepr.__Iterator(self)
  def __determineClassDerivationDepth(self, node):
    max_super_depth = -1
    for super in node.Supers():
      super_depth = self.classes[super].depth if super in self.classes else 0
      if super_depth > max_super_depth:
        max_super_depth = super_depth
    return max_super_depth + 1
  
class CodeGenRepr:
  '''
  Top level code generation representation type for a Dia diagram.
  '''
  def __init__(self, diagram, filename):
    '''
    Stores passed filename and uses passed diagram object to
    extract and create the internal code generation representation.
    '''
    self.__dia = diagram
    self.__fname = filename
    self.__classes = ClassDiagRepr()
    for l in diagram.layers:
      self.__ProcessLayer(l)
  def __ProcessLayer(self, layer):
    for o in layer.objects:
      if self.__isUMLClassObject(o):
        self.__ProcessClassObject(o)
    # TODO: Handle other possibly interesting UML diagram layer objects:
    #  "UML - Association" "UML - Note", "UML - LargePackage"
    # , "UML - SmallPackage", "UML - Dependency", ...
  def __isUMLClassObject(self, object):
    return object.type.name == "UML - Class"
  def __ProcessClassObject(self, object):
    self.__classes[object.properties["name"].value] = object
  def Filename(self):
    '''
    Returns the file name to write generated code to
    '''
    return self.__fname
  def Classes(self):
    '''
    Return a subscriptable on class name and iterable representation of
    of the class diagram.
    '''
    return self.__classes
  def ClassesDiagram(self):
    '''
    Return the original Dia diagram object passed to __init__
    '''
    return self.__dia
 
class CodeGenRenderer:
  '''
  Dia export renderer. 
  Hands processing over to instances of:
   - diagramReprClass : 
  a class whose instances are a code generation
  representation of a diagram and a code writing class, an instance of which
  is created from an instance of the representation class and writes out the
  generated code.
  '''
  def __init__(self, codeWriterClass, diagramReprClass=CodeGenRepr):
    self.writerClass = codeWriterClass
    self.diaReprClass = diagramReprClass

  def begin_render(self, diagram, filename):
    '''
    Creates and stores an instance of the code generation representation of
    a diagram class, passing its initialiser the diagram and filename
    parameter values.
    '''
    self.repr = self.diaReprClass(diagram,filename)

  def end_render(self):
    '''
    Creates an instance of the writer class that in doing so writes code to
    the file. It is passed the code generation representation object created 
    in begin_render.
    '''
    writer = self.writerClass(self.repr)
    self.repr = None # Indicate representation resources are garbage

class PythonWriter:
  '''
  Code writer class for Python.
  '''
  def __init__(self, repr):
    '''
    Opens file specified in repr and writes a Python version of the
    the classes represented by repr.
    '''
    self.out = open(repr.Filename(),"w")
    self.out.write("# Generated by Dia via nextcodegen.py\n")
    for cprops in repr.Classes():
      self._writeClass(cprops)
  def _writeClass(self, props):
    quals = ''
    if props.IsAbstract():
      quals = 'abstract '
    if props.IsTemplate():
      quals = ''.join([quals, ', template'])
    quals = ConditionallyPrefix(' # ', quals)
    name = props.Name()
    if not props.Superclasses():
      self.out.write("\nclass %s:%s\n" % (name, quals))
    else:
      bases = ''
      for b in props.Superclasses():
        bases = ','.join([bases,b])
      bases = bases[1:]
      self.out.write("\nclass %s(%s):%s\n" % (name, bases ,quals))
    self._conditionallyWriteDocComment(props.Comment(),NCGenConfig.indent)
    self._writeClassAttributes(props.Attributes())
    self._writeInitAttributes(props.Attributes(), props.Operations())
    self._writeOperations(props.Operations())
  def _writeClassAttributes(self, attribs):
    for a in attribs.itervalues():
      if a.HasClassScope():
        self.out.write("%s%s%s%s\n"
                       %  ( NCGenConfig.indent, a.name
                          , ConditionallyPrefix(" = ", a.Value())
                          , ConditionallyPrefix(" # ", a.Comment()))
                      )
  def _writeOperations(self, ops):
    for overrides in ops.itervalues():
      for o in overrides:
        if o.Name() == "__init__":
          continue # skip __init__, handled elsewhere
        indent = NCGenConfig.indent
        if o.HasClassScope():
          self.out.write("%s@classmethod\n" % indent)
        self.out.write("%sdef %s(%s)%s\n"
                       % ( indent
                         , o.Name()
                         , self._strParameters(o.Parameters(), isClassMethod=o.HasClassScope())
                         , ConditionallyPrefix(" # -> ", o.Type()))
                      )
        indent = indent * 2
        if o.Comment():
          self.out.write("%s''' %s '''\n" % (indent, o.Comment()))
        self.out.write("%spass\n" % indent)
  def _writeInitAttributes(self, attribs, ops):
    def attribHasParam(attrib,params):
      for p in params:
        if p.Name() == attrib.Name():
          return True
      return False

    params = None
    comment = None
    if "__init__" in ops:
      params = ops["__init__"][0].Parameters()
      comment = ops["__init__"][0].Comment()
    else:
      params = []
    indent = NCGenConfig.indent
    self.out.write("%sdef __init__(%s)\n"
                   % (indent, self._strParameters(params)))
    indent = indent * 2
    self._conditionallyWriteDocComment(comment,indent)
    strAttribs = ''
    for a in attribs.itervalues():
      if not a.HasClassScope():
        strAttribs = ''.join([strAttribs,indent,"self.", a.Name(), " = "
                              , a.Name() if attribHasParam(a,params) else "None", "\n"])
    self.out.write(strAttribs if strAttribs else "%spass\n"%indent)
  def _strParameters(self, params, isClassMethod=False):
    strParams = 'cls' if isClassMethod else 'self'
    for p in params:
      strParams = ''.join([strParams,', ',p.Name(),ConditionallyPrefix("=",p.Value())])
    return strParams
  def _conditionallyWriteDocComment(self, comment, indent):
    if comment and (comment!="(NULL)"):
      self.out.write("%s''' %s '''\n" % (indent, comment))

class PythonCodeGenRenderer(CodeGenRenderer):
  '''
  Python specific subclass of CodeGenRenderer that hard-wires
  the writer class to be PythonWriter.
  '''
  def __init__(self):
    CodeGenRenderer.__init__(self, PythonWriter)

# Register the code generation export renderers with Dia
dia.register_export ("Next Gen Dia Code Generation (Python)", "py", PythonCodeGenRenderer())

