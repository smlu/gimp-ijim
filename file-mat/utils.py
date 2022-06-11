from gimpfu import *

def is_layer_mipmap(img):
    para = img.parasite_find('mipmap')
    if para:
        return para.flags
    return False

def set_layer_as_mipmap(layer, is_mipmap):
    layer.attach_new_parasite('mipmap', is_mipmap, '')

def make_mipmap_lods(layer, min_size = 1, max_level = -1):
    """Returns list of MipMap layers"""
    if min_size < 1 or max_level == 0: return  []
    lods = []
    img = layer.image
    lod_width  = layer.width >> 1
    lod_height = layer.height >> 1
    while(lod_width >= min_size and lod_height >= min_size and max_level - 1 != 0):
        l = pdb.gimp_layer_new_from_drawable(layer, img)
        img.add_layer(l)
        l.scale(lod_width, lod_height)
        lods.append(l.get_pixel_rgn(0, 0, l.width, l.height))
        lod_width  = lod_width >> 1
        lod_height = lod_height >> 1
        max_level -= 1

    return lods

def sanitize_image(img):
    # src: https://gitlab.gnome.org/GNOME/gimp/blob/master/app/file/file-open.c#L730

    # Enable image undo
    while(not img.undo_is_enabled()):
        img.undo_thaw()

    img.clean_all()
