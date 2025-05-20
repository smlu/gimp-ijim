# File-MAT GIMP plugin
# Copyright (c) 2019-2025 Crt Vavros

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, Gegl
from typing import List

def is_layer_mipmap(layer: Gimp.Layer) -> bool:
    """
    Check whether the given layer has a 'mipmap' parasite attached.
    """
    par = layer.get_parasite('mipmap')
    return par and par.get_data() == [1]

def set_layer_as_mipmap(layer: Gimp.Layer, is_mipmap: bool) -> None:
    """
    Attach or update the 'mipmap' parasite on a layer.
    """
    # Remove any existing mipmap parasite
    layer.detach_parasite('mipmap')

    parasite = Gimp.Parasite.new(
        name  = 'mipmap',
        flags = 1, # 1-persistent
        data  = [1 if is_mipmap else 0]
    )
    layer.attach_parasite(parasite)

def make_mipmap_lods(layer: Gimp.Layer, min_size: int = 1, max_level: int = -1) -> List[Gegl.Buffer]:
    """
    Generate a list of pixel regions for successive Mipmap levels of `layer`.
    Stops when either dimension falls below min_size or max_level is exhausted.
    """
    if min_size < 1 or max_level == 0:
        return []

    img  = layer.get_image()
    lods = []

    lod_width  = layer.get_width()  // 2
    lod_height = layer.get_height() // 2

    level = max_level
    while lod_width >= min_size and lod_height >= min_size and level != 0:
        # Clone the layer
        new_layer = layer.copy()
        img.insert_layer(new_layer, None, -1)

        # Scale it down and attach list
        # Note: the scale will apply sRGB conversion and the mipmap images will be slightly brighter than the original
        new_layer.scale(lod_width, lod_height, local_origin=False) 
        lods.append(new_layer.get_buffer())

        # Prepare next level
        lod_width  //= 2
        lod_height //= 2
        level       -= 1

    return lods


def sanitize_image(img: Gimp.Image) -> None:
    # src: https://gitlab.gnome.org/GNOME/gimp/-/blob/GIMP_3_0_2/app/file/file-open.c?ref_type=tags#L759
    while not img.undo_is_enabled():
        img.undo_thaw()
    # Clear all undo history
    img.clean_all()