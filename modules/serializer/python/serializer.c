#include "py_defines.h"
#include "version.h"

#define GETSTATE(m) ((struct module_state*)PyModule_GetState(m))

const char *datetime_type = "DateTimeField";
const char *referencefield_type = "ReferenceField";
const char *filefield_type = "FileField";
const char *choicefield_type = "ChoiceField";
const char *hyperlinkedfield_type = "HyperlinkedField";

static PyObject * _isoformat(PyObject *value);
static PyObject * _serialize_value(PyObject *obj, PyObject *field_name, PyObject *field, char *type_name);


static PyObject * serialize(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *obj, *fields;
    
    static char *kwlist[] = {"obj", "fields", NULL};

    // Process params
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO", kwlist, &obj, &fields))
        return NULL;

    PyObject *dict = PyDict_New();
    PyObject *field;

    PyObject *iterator = PyObject_GetIter(fields);
    if (iterator == NULL)
        return NULL;

    // Main loop per field
    while (!PyErr_Occurred() && (field = PyIter_Next(iterator))) {
        PyObject *field_name = PyObject_GetAttrString(field, "field_name");
        PyObject *type_name = PyObject_GetAttrString(field, "type_name");

        char *type_name_c = NULL;
        if (type_name == NULL) {
            // Fallback to getting class
            PyErr_Clear();
            PyObject *klass = PyObject_GetAttrString(field, "__class__");
            type_name = PyObject_GetAttrString(klass, "__name__");
            Py_DECREF(klass);
        }

        if (type_name != NULL) {
            if (PyUnicode_Check(type_name)) {
                PyObject *type_name_str = PyUnicode_AsUTF8String(type_name);
                Py_DECREF(type_name);
                type_name = type_name_str;
                type_name_c = PyString_AS_STRING(type_name_str);
            } else {
                type_name_c = PyString_AS_STRING(type_name);
            }
        }

        // Check if it is a write only field - which we should ignore
        PyObject *is_write_only = PyObject_GetAttrString(field, "write_only");
        if (is_write_only == NULL) {
            PyErr_Clear();
        }

        if (is_write_only == NULL || is_write_only == Py_False) {
            PyObject *value = _serialize_value(obj, field_name, field, type_name_c);
            if (value != NULL) {
                PyDict_SetItem(dict, field_name, value);
                Py_DECREF(value);
            }
        }

        Py_XDECREF(is_write_only);
        Py_XDECREF(type_name);
        Py_XDECREF(field_name);
        Py_DECREF(field);
    }

    Py_DECREF(iterator);

    if (PyErr_Occurred())
        return NULL;
    
    return dict;
}

static PyObject * _serialize_value(PyObject *obj, PyObject *field_name, PyObject *field, char *type_name) {
    PyObject *value = NULL;

    // Right now only datetime gets custom behavior as default formatting is slow
    if (type_name != NULL && strcmp(type_name, datetime_type)==0) {
        value = PyObject_GetAttr(obj, field_name);

        if (value == NULL) {
            PyErr_Format(PyExc_TypeError, "Invalid fields definition, missing field");
            return NULL;
        } else {
            if (value != Py_None && type_name != NULL) {
                PyObject *iso_value = _isoformat(value);
                Py_DECREF(value);
                value = iso_value;

                // Serialize as dict structure when needed
                PyObject *as_dict = PyObject_GetAttrString(field, "as_dict");
                if (as_dict == NULL) {
                    PyErr_Clear();
                } else if (as_dict != Py_False) {
                    PyObject *value_dict = PyDict_New();
                    PyDict_SetItemString(value_dict, "type", as_dict);
                    PyDict_SetItemString(value_dict, "value", value);
                    Py_DECREF(as_dict);
                    Py_DECREF(value);

                    value = value_dict;
                }
            }
        }
    } else {
        value = PyObject_CallMethod(field, "get_attribute", "(O)", obj);
        if (value != Py_None) {
            PyObject *ret = PyObject_CallMethod(field, "to_representation", "(O)", value);
            Py_DECREF(value);
            return ret;
        }
    }
    return value;
}

static PyObject * isoformat(PyObject *self, PyObject *args) {
    PyObject *value;
    
    if (!PyArg_ParseTuple(args, "O", &value))
        return NULL;

    return _isoformat(value);
}

static PyObject * _isoformat(PyObject *value) {
    return PyUnicode_FromFormat("%d-%02d-%02dT%02d:%02d:%02d.%06dZ", PyDateTime_GET_YEAR(value),
                                PyDateTime_GET_MONTH(value), PyDateTime_GET_DAY(value),
                                PyDateTime_DATE_GET_HOUR(value), PyDateTime_DATE_GET_MINUTE(value),
                                PyDateTime_DATE_GET_SECOND(value), PyDateTime_DATE_GET_MICROSECOND(value));
}

static PyMethodDef serializerMethods[] = {
    {"serialize",  (PyCFunction)serialize, METH_KEYWORDS|METH_VARARGS, "Serializes object to dict."},
    {"isoformat",  (PyCFunction)isoformat, METH_VARARGS, "Formats datetime object as ISO 8601."},
    {NULL, NULL}
};

static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "serializer",
        NULL,
        -1,
        serializerMethods,
        NULL,
        NULL,
        NULL,
        NULL
};

PyMODINIT_FUNC PyInit_serializer(void) {
    PyDateTime_IMPORT;
    return PyModule_Create(&moduledef);
}

