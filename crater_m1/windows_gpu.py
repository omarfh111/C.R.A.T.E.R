"""DXGI adapter enumeration so DirectML selects the dedicated laptop GPU."""
import ctypes
import sys
import uuid


def adapters():
    if sys.platform!="win32": return []
    class Description(ctypes.Structure):
        _fields_=[("name",ctypes.c_wchar*128),("vendor",ctypes.c_uint),("device",ctypes.c_uint),
            ("subsystem",ctypes.c_uint),("revision",ctypes.c_uint),("dedicated_video",ctypes.c_size_t),
            ("dedicated_system",ctypes.c_size_t),("shared_system",ctypes.c_size_t),
            ("luid_low",ctypes.c_uint),("luid_high",ctypes.c_int),("flags",ctypes.c_uint)]
    def method(obj,index,return_type,*arguments):
        table=ctypes.cast(obj,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(return_type,ctypes.c_void_p,*arguments)(table[index])
    iid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID("770aae78-f26f-4dba-a829-253c83d1b387").bytes_le)
    factory=ctypes.c_void_p();create=ctypes.WinDLL("dxgi").CreateDXGIFactory1
    create.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)];create.restype=ctypes.c_long
    if create(ctypes.byref(iid),ctypes.byref(factory))<0: raise RuntimeError("DXGI factory unavailable")
    result=[]
    try:
        for index in range(16):
            adapter=ctypes.c_void_p()
            status=method(factory,12,ctypes.c_long,ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p))(factory,index,ctypes.byref(adapter))
            if status<0: break
            try:
                desc=Description()
                if method(adapter,10,ctypes.c_long,ctypes.POINTER(Description))(adapter,ctypes.byref(desc))<0:
                    raise RuntimeError("DXGI adapter description unavailable")
                if not desc.flags&2:
                    result.append({"device_id":index,"name":desc.name,"vendor_id":desc.vendor,
                        "dedicated_video_mb":round(desc.dedicated_video/1048576)})
            finally: method(adapter,2,ctypes.c_ulong)(adapter)
    finally: method(factory,2,ctypes.c_ulong)(factory)
    return result


def preferred_adapter(items):
    if not items: raise RuntimeError("No DirectML hardware adapter found")
    return max(items,key=lambda item:(item["vendor_id"]==0x10de,item["dedicated_video_mb"]))
