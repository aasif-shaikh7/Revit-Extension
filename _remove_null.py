# -*- coding: utf-8 -*-
import os

target = r"C:\Users\pc-1\Desktop\Revit-Extension\$null"
print("exists:", os.path.exists(target))
try:
    os.remove(target)
    print("removed")
except Exception as e:
    print("error:", e)
print("after:", os.path.exists(target))