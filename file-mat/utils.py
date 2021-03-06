from gimpfu import *

def is_image_mipmap(img):
    para = img.parasite_find("mipmap")
    if para:
        return para.flags
    return False

def set_image_as_mipmap(img, is_mipmap):
    img.attach_new_parasite("mipmap", is_mipmap, "")

def make_mipmaps(img, min_size = 1, max_level = -1):
    if min_size < 1 or max_level == 0: return  []
    mipmaps = []
    mip_width  = img.width >> 1
    mip_height = img.height >> 1
    while(mip_width >= min_size and mip_height >= min_size and max_level - 1 != 0):
        mip = img.duplicate()
        mip.scale(mip_width, mip_height)
        #pdb.gimp_image_scale_full(mip, mip_width, mip_height, INTERPOLATION_CUBIC)
        #pdb.gimp_image_scale(mip, mip_width, mip_height)
        mip.merge_visible_layers(CLIP_TO_IMAGE)

        mipmaps.append(mip)
        mip_width  = mip_width >> 1
        mip_height = mip_height >> 1
        max_level -= 1

    return mipmaps

def sanitize_image(img):
    # src: https://gitlab.gnome.org/GNOME/gimp/blob/master/app/file/file-open.c#L730

    # Enable image undo
    while(not img.undo_is_enabled()):
        img.undo_thaw()

    img.clean_all()
