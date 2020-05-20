from gimpfu import *
from utils import *

from array import array
from collections import namedtuple
from struct import *
import os

MAT_FILE_MAGIC       = b'MAT '
MAT_REQUIRED_VERSION = 0x32
MAT_REQUIRED_TYPE    = 2

# Class for loading and exporting images to material file
# for game Indiana Jones and the Infernal Machine
# Note: on destruction internal stored images are deleted
class MAT:
    def __init__(self, display_lod = False):
        self._imgs = []
        self._display_lod = display_lod

    def __del__(self):
        self.clear()

    def load_from_file(self, file_path, max_mmaps = -1):
        self.clear()

        f = open(file_path, 'rb')
        h = self._read_header(f)
        r = self._read_records(f, h)

        mat_name  = file_path #os.path.basename(file_path)
        max_mmaps = h.mipmap_count if max_mmaps < 0 else max_mmaps
        for mm_idx in range(0, max_mmaps):
            mm = self._read_mipmap(f, h.color_info)
            for tex_idx, tex in enumerate(mm.pixel_data_array):
                img_width  = mm.width  >> tex_idx
                img_height = mm.height >> tex_idx
                img_name   = self._get_tex_name(mm_idx, tex_idx, mat_name)

                img = MAT._make_image(tex, img_width, img_height, mm.color_info)
                img.filename = img_name

                sanitize_image(img)

                if tex_idx == 0 and len(mm.pixel_data_array) > 1:
                    set_image_as_mipmap(img, True)
                self._imgs.append(img)

                # Skip displaying mipmaps LOD textures?
                if not self._display_lod:
                    break

    def save_to_file(self, file_path, bpp, min_mipmap_size = 8, max_mipmap_level = 4): # 
        if bpp != 16 and bpp != 32:
            raise ValueError("bpp argument must be 16 or 32")

        if os.path.exists(file_path):
            os.remove(file_path)

        f = open(file_path, 'wb')
        img_count = len(self._imgs)

        #Show progress
        gimp.progress_init("Exporting %d %s as MAT" % (img_count, "image" if img_count == 1 else "images"))

        cf = MAT._write_header(f, img_count, bpp, self._has_alpha())
        MAT._write_records(f, img_count)

        for idx, i in enumerate(self._imgs):
            MAT.write_mipmap(f, i, cf, min_mipmap_size, max_mipmap_level)
            gimp.progress_update(idx / float(img_count))

    @property
    def images(self):
        return self._imgs

    def get_images_copy(self):
        dlist = []
        for i in self._imgs:
            dlist.append( i.duplicate() )
        return dlist

    def clear(self):
        for i in self._imgs:
            try:
                pdb.gimp_image_delete(i)
            except: pass



    INDEXED, RGB, RGBA,  = range(3)

    color_format = namedtuple('color_format', [
        'color_mode',
        'bpp',
        'red_bpp', 'green_bpp', 'blue_bpp',
        'red_shl', 'green_shl', 'blue_shl',
        'red_shr', 'green_shr', 'blue_shr',
        'alpha_bpp', 'alpha_shl', 'alpha_shr'
    ])
    cf_serf = Struct('<14I')


    mat_header = namedtuple('mat_header', [
        'magic',
        'version',
        'type',
        'record_count',
        'mipmap_count',
        'color_info'
    ])
    mh_serf = Struct('<4siIii')


    mat_record_header = namedtuple('mat_record_header', [
        'record_type',
        'transparent_color',
        'unknown_1',
        'unknown_2',
        'unknown_3',
        'unknown_4',
        'unknown_5',
        'unknown_6',
        'unknown_7',
        'mipmap_idx'
    ])
    mrh_serf = Struct('<10i')


    mat_mipmap_header = namedtuple('mat_mipmap_header', [
        'width',
        'height',
        'transparent',
        'unknown_1',
        'unknown_2',
        'texture_count',
    ])
    mmm_serf = Struct('<6i')


    mipmap = namedtuple("mipmap", [
        'width',
        'height',
        'color_info',
        'pixel_data_array'
    ])

    def _has_alpha(self):
        for i in self._imgs:
            if i.active_layer and i.active_layer.has_alpha:
                return True
        return False


    @staticmethod
    def make_color_format(bpp, alpha):
        if bpp == 16:
            if alpha:
                return MAT.color_format(MAT.RGBA, bpp, 4,4,4, 12,8,4, 4,4,4, 4,0,4) #RGBA4444
            return MAT.color_format(MAT.RGB, bpp, 5,6,5, 11,5,0, 3,2,3, 0,0,0) #RGB565
        elif bpp == 32:
            if alpha:
                return MAT.color_format(MAT.RGBA, bpp, 8,8,8, 24,16,8, 0,0,0, 8,0,0) #RGBA8888
            return MAT.color_format(MAT.RGB, 24, 8,8,8, 16,8,0, 0,0,0, 0,0,0) #RGB888

        raise ValueError("Cannot crate ColorFormat, invalid bpp: " + str(bpp))

    @staticmethod
    def _read_header(f):
        rh  = bytearray( f.read(MAT.mh_serf.size) )
        rcf = bytearray( f.read(MAT.cf_serf.size) )

        deser_mh = MAT.mh_serf.unpack(rh)
        cf       = MAT.color_format._make( MAT.cf_serf.unpack(rcf) )

        h = MAT.mat_header(deser_mh[0], deser_mh[1], deser_mh[2], deser_mh[3], deser_mh[4], cf) #was h = mat_header(*mh_serf.unpack(rh), cf)
        if h.magic != MAT_FILE_MAGIC:
            raise ImportError("Invalid MAT file")
        if h.version != MAT_REQUIRED_VERSION:
            raise ImportError("Invalid MAT file version")
        if h.type != MAT_REQUIRED_TYPE:
            raise ImportError("Invalid MAT file type")
        if h.record_count != h.mipmap_count:
            raise ImportError("Cannot read older version of MAT file")
        if h.record_count <= 0:
            raise ImportError("MAT file record count <= 0")
        if not ( MAT.INDEXED < h.color_info.color_mode <= MAT.RGBA ): # must not be indexed color mode (0)
            raise ImportError("Invalid color mode")
        if h.color_info.bpp % 8 != 0:
            raise ImportError("BPP % 8 != 0")
        return h

    @staticmethod
    def _write_header(f, tex_count, bpp, alpha):
        cf = MAT.make_color_format(bpp, alpha)
        h = MAT.mat_header(MAT_FILE_MAGIC, MAT_REQUIRED_VERSION, MAT_REQUIRED_TYPE, tex_count, tex_count, cf)

        rh  = MAT.mh_serf.pack(*h[0:5]) # not including 'color_info' field
        rcf = MAT.cf_serf.pack(*cf)
        f.write(rh)
        f.write(rcf)
        return cf

    @staticmethod
    def _read_records(f, h):
        rh_list = []
        for i in range(0, h.record_count):
            #rc  = h.record_count
            mrh = MAT.mrh_serf.unpack(bytearray( f.read(MAT.mrh_serf.size) ))
            rh_list.append( MAT.mat_record_header._make(mrh) )
        return rh_list

    @staticmethod
    def _write_records(f, record_count):
        record_type = 8
        for i in range(0, record_count):
            r = MAT.mat_record_header(record_type, 0, 0, 0, 0, 0, 0, 0, 0, i)
            f.write( MAT.mrh_serf.pack(*r) )

    @staticmethod
    def _get_img_row_len(width, bpp):
        return int(abs(width) * (bpp /8))

    @staticmethod
    def _get_pixel_data_size(width, height, bpp):
        return int( abs(width * height) * (bpp /8) )

    @staticmethod
    def _get_encoded_pixel_size(bpp):
        return int(bpp /8)

    @staticmethod
    def _get_decoded_pixel_size(ci):
        return 4 if ci.alpha_bpp != 0 else 3

    @staticmethod
    def _get_color_mask(bpc):
        return 0xFFFFFFFF >> (32 - bpc)

    @staticmethod
    def _decode_pixel(p, ci): # p: int, ci: color_format
        r = ((p >> ci.red_shl)   & MAT._get_color_mask(ci.red_bpp))   << ci.red_shr
        g = ((p >> ci.green_shl) & MAT._get_color_mask(ci.green_bpp)) << ci.green_shr
        b = ((p >> ci.blue_shl)  & MAT._get_color_mask(ci.blue_bpp))  << ci.blue_shr

        # Return pixel representation
        if ci.alpha_bpp != 0:
            a = ((p >> ci.alpha_shl) & MAT._get_color_mask(ci.alpha_bpp)) << ci.alpha_shr
            p = (int(r), int(g), int(b), int(a))
        else:
            p = (int(r), int(g), int(b))
        return array("B", p)

    @staticmethod
    def _encode_pixel(p, ci): # p: array, ci: color_format
        r = p[0]
        g = p[1]
        b = p[2]

        e_p = ((r >> ci.red_shr)   << ci.red_shl)   | \
              ((g >> ci.green_shr) << ci.green_shl) | \
              ((b >> ci.blue_shr)  << ci.blue_shl)

        if ci.alpha_bpp != 0:
            a    = p[3] if len(p) == 4 else 255
            e_p |= ((a >> ci.alpha_shr) << ci.alpha_shl)

        return int(e_p)

    @staticmethod
    def _decode_pixel_data(pd, width, height, ci): # ci: color_format
        pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        row_len    = MAT._get_img_row_len(width, ci.bpp)

        d_pixel_size = MAT._get_decoded_pixel_size(ci)
        d_row_len    = d_pixel_size * width
        dpd          = array("B", "\x00" * (height * d_row_len))

        # decode pixel little endian if not 24bpp
        # decode pixel as big endian if 24bpp
        fmt = "B" if pixel_size == 1 else "<H" if pixel_size == 2 else ">I" if pixel_size == 3 else "<I"
        for r in range(0, height):
            for c in range(0, row_len, pixel_size):
                i = c + r * row_len
                p_raw = pd[i: i + pixel_size]
                if pixel_size == 3:
                    p_raw = bytearray(1) + p_raw# Note: might not work for bigendian
                pixel = int(unpack(fmt, p_raw)[0])

                d_pos = (c / pixel_size) * d_pixel_size  + r * d_row_len
                dpd[d_pos : (d_pos + d_pixel_size)] =  MAT._decode_pixel(pixel, ci)
        return dpd

    @staticmethod
    def _encode_pixel_region(pr, ci): # pr: gimp.PixelRegion ci: color_format
        width        = pr.w
        height       = pr.h
        #pixel_size   = pr.bpp
        #row_len      = MAT._get_img_row_len(width, pr.bpp * 8)

        e_pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        e_row_len    = e_pixel_size * width
        epd          = array("B", "\x00" * (height * e_row_len))

        # encode pixel little endian if not 24bpp
        # encode pixel as big endian if 24bpp
        fmt = "B" if e_pixel_size == 1 else "<H" if e_pixel_size == 2 else ">I" if e_pixel_size == 3 else "<I"
        for y in range(0, height):
            for x in range(0, width):
                p   = tuple(array("B",pr[x, y]))
                e_p = MAT._encode_pixel(p, ci)
                e_p = array("B", pack(fmt, e_p))
                if e_pixel_size == 3:
                    e_p = e_p[1::]

                e_pos = x * e_pixel_size  + y * e_row_len
                epd[e_pos : (e_pos + e_pixel_size)] = e_p
        return epd

    @staticmethod
    def _read_texture(f, width, height, ci): # f: file ci: color_format
        pd_size = MAT._get_pixel_data_size(width, height, ci.bpp)
        pd = bytearray(f.read(pd_size))
        return MAT._decode_pixel_data(pd, width, height, ci)

    @staticmethod
    def _write_texture(f, pr, ci): # f: file pr: gimp.PixelRegion ci: color_format
        epd = MAT._encode_pixel_region(pr, ci)
        f.write(epd)

    @staticmethod
    def _read_mipmap(f, ci): # f: file ci: color_format
        mmh_raw = MAT.mmm_serf.unpack(bytearray( f.read(MAT.mmm_serf.size) ))
        mmh     = MAT.mat_mipmap_header._make(mmh_raw)

        pd = []
        for i in range(0, mmh.texture_count):
            tex_w = mmh.width  >> i
            tex_h = mmh.height >> i
            pd += [ MAT._read_texture(f, tex_w, tex_h, ci) ]

        return MAT.mipmap(mmh.width, mmh.height, ci, pd)

    @staticmethod
    def write_mipmap(f, img, ci, min_mipmap_size, max_mipmap_level): # f:file, img:image, ci:color_format, min_mipmap_size:int, max_mipmap_level:int
        imgs = [img]
        if (is_image_mipmap(img)):
            imgs += make_mipmaps(img, min_mipmap_size, max_mipmap_level)

        mmh = MAT.mat_mipmap_header(img.width, img.height, 0, 0, 0, len(imgs))
        f.write( MAT.mmm_serf.pack(*mmh) )

        for idx, i in enumerate(imgs):
            l = i.active_layer
            pr = l.get_pixel_rgn(0, 0, l.width, l.height)
            MAT._write_texture(f, pr, ci)

            if idx > 0:
                pdb.gimp_image_delete(i)


    @staticmethod
    def _get_tex_name(mmap_idx, tex_idx, mat_name):
        name = os.path.splitext(mat_name)[0]
        if mmap_idx > 0:
            name += '_' + str(mmap_idx)
        if tex_idx > 0:
            name += '_' + str(tex_idx)
        return name

    @staticmethod
    def _make_image(tex, width, height, ci):
        img   = gimp.Image(width, height, RGB)
        layer = gimp.Layer(img, "", img.width, img.height, RGB_IMAGE, 100, NORMAL_MODE)
        if ci.alpha_bpp != 0:
            layer.add_alpha()

        pr = layer.get_pixel_rgn(0, 0, layer.width, layer.height)
        pr[:,:] = tex.tostring()

        layer.flush()
        img.add_layer(layer)

        return img
