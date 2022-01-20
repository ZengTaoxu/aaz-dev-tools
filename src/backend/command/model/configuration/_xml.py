import inflect
import re

from lxml.builder import ElementMaker
from lxml.etree import Element, tostring
from xmltodict import parse

from schematics.types import ListType, ModelType
from schematics.types.compound import PolyModelType
from schematics.types.serializable import Serializable

from command.model.configuration import CMDHelp

XML_ROOT = "CodeGen"


class XMLSerializer:

    def __init__(self, model):
        self.model = model

    def to_xml(self):
        primitive = self.model.to_primitive()
        root = build_xml(primitive)
        return self._unescape(
            tostring(root, xml_declaration=True, pretty_print=True, encoding="utf-8").decode()
        )

    def from_xml(self, fp):
        primitive = parse(self._escape(fp.read()), attr_prefix="")
        return build_model(self.model, primitive[XML_ROOT])

    @classmethod
    def _unescape(cls, s):
        return re.sub(r'"array&lt;(.+)&gt;"', '"array<\\1>"', s)

    @classmethod
    def _escape(cls, s):
        return re.sub(r'"array<(.+)>"', '"array&lt;\\1&gt;"', s)


def build_xml(primitive, parent=None):
    if parent is None:
        parent = getattr(ElementMaker(), XML_ROOT)()
    # normalize element name
    if singular := _inflect_engine.singular_noun(parent.tag):
        parent.tag = singular

    for field_name, data in primitive.items():
        primitive_to_xml(field_name, data, parent)
    return parent


def primitive_to_xml(field_name, data, parent):
    if isinstance(data, dict):
        _parent = getattr(ElementMaker(), field_name)()
        parent.append(build_xml(data, _parent))
    elif isinstance(data, list):
        for d in data:
            primitive_to_xml(field_name, d, parent)
    else:
        # handle long-summary
        if field_name == "p":
            child = Element("p")
            child.text = str(data)
            parent.append(child)
        # store metadata as attributes
        elif prev := parent.get(field_name):
            curr = " ".join(sorted(f"{prev} {data}".split(), key=len, reverse=True))
            parent.set(field_name, curr)
        else:
            parent.set(field_name, str(data))


def build_model(model, primitive):
    if hasattr(model, "_field_list"):
        instance = model()
        for field_name, field in model._field_list:
            if isinstance(field, Serializable):
                continue
            # obtain corresponding tag
            serialized_name = field.serialized_name or field_name
            if serialized_name in primitive:
                curr_tag = serialized_name
            elif (singular := _inflect_engine.singular_noun(serialized_name)) in primitive:
                curr_tag = singular
            else:
                continue
            data = primitive[curr_tag]
            curr_field = unwrap(field)
            field_value = obtain_field_value(field, curr_field, data)
            setattr(instance, field_name, field_value)
        return instance
    else:
        # handle primitive field
        cast = model.primitive_type or str
        if primitive == "0":
            return 0
        return cast(primitive)


def obtain_field_value(prev, curr, data):
    if isinstance(prev, ListType):
        field_value = []
        # distinguish options and long-summary
        if " " in data and not issubclass(curr.owner_model, CMDHelp):
            data = data.split()
        if isinstance(data, list):
            for d in data:
                model = curr.find_model(d) if isinstance(curr, PolyModelType) else curr
                value = build_model(model, d)
                field_value.append(value)
        else:
            model = curr.find_model(data) if isinstance(curr, PolyModelType) else curr
            value = build_model(model, data)
            field_value.append(value)
    else:
        model = curr.find_model(data) if isinstance(curr, PolyModelType) else curr
        field_value = build_model(model, data)
    return field_value


def unwrap(field):
    if isinstance(field, ListType):
        return unwrap(field.field)
    elif isinstance(field, ModelType):
        return field.model_class
    else:
        return field


_inflect_engine = inflect.engine()