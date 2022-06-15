# File-MAT GIMP plugin
# Copyright (c) 2019-2022 Crt Vavros

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

from gimpfu import *
from utils import *

from array import array
from collections import namedtuple
from struct import *
import os

MAT_FILE_MAGIC       = b'MAT '
MAT_REQUIRED_VERSION = 0x32
MAT_REQUIRED_TYPE    = 2

class MAT:
    """
    Class for loading and saving image to MAT file format
    for Indiana Jones and the Infernal Machine game.
    """

    def load_from_file(self, file_path, max_cells = -1, load_mipmap_lod_chain = False):
        '''
        Loads MAT from file and returns image.
        :param file_path: path to the MAT file
        :param max_cells: max number of celluloid textures to load.
                          Default -1, meaning all.
        :param load_mipmap_lod_chain: Loads MipMap texture LOD images as layers. If false no LOD image is loaded.
        '''
        f = open(file_path, 'rb')
        h = self._read_header(f)
        r = self._read_records(f, h)

        max_cells = h.cel_count if max_cells < 0 else min(max_cells, h.cel_count)
        width, height = (1,1)
        img = gimp.Image(1, 1, RGB)
        img.filename = os.path.splitext(file_path)[0]
        for cel_idx in range(0, max_cells):
            mm = self._read_texture(f, h.color_info)
            for lod_num, pixdata in enumerate(mm.pixel_data_array):
                lwidth  = mm.width  >> lod_num
                lheight = mm.height >> lod_num

                if lwidth > width or lheight > height:
                    width  = max(lwidth, width)
                    height = max(lheight, height)
                    img.resize(width, height)

                l = MAT._add_layer(img, pixdata, lwidth, lheight, mm.color_info)
                l.name = self._get_layer_name(cel_idx, lod_num)
                if cel_idx > 0:
                    l.visible = False

                #img = MAT._make_image(pixdata, img_width, img_height, mm.color_info)
                #img.filename = img_name

                if lod_num == 0 and len(mm.pixel_data_array) > 1:
                    set_layer_as_mipmap(l, True)

                # Skip loading LOD images?
                if not load_mipmap_lod_chain:
                    break

        sanitize_image(img)
        #self._imgs.append(img)
        return img

    def save_to_file(self, file_path, img, cf, lod_min_size = 8, lod_max_levels = 4):
        '''
        Save MAT to file.
        :param file_path: file path where to save MAT
        :param img: The image to save in MAT file format
        :param cf: The color format to encode texture bitmap
        :param lod_min_size: minimum MipMap LOD image size
        :param lod_max_levels: maximum number of MipMap levels
        '''
        if os.path.exists(file_path):
            os.remove(file_path)

        f = open(file_path, 'wb')
        cel_count = len(img.layers)

        #Show progress
        gimp.progress_init('Exporting {} image {} to MAT'.format(cel_count, 'layer' if cel_count == 1 else 'layers'))

        self._write_header(f, cel_count, cf)
        self._write_records(f, cel_count)

        for idx, l in enumerate(reversed(img.layers)):
            self.write_texture(f, l, cf, lod_min_size, lod_max_levels)
            gimp.progress_update(idx / float(cel_count))

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
        'cel_count',
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
        'cel_idx'
    ])
    mrh_serf = Struct('<10i')

    mat_mipmap_header = namedtuple('mat_mipmap_header', [
        'width',
        'height',
        'transparent',
        'unknown_1',
        'unknown_2',
        'mipmap_levels',
    ])
    mmm_serf = Struct('<6i')

    mipmap = namedtuple('mipmap', [
        'width',
        'height',
        'color_info',
        'pixel_data_array'
    ])

    @staticmethod
    def _read_header(f):
        rh  = bytearray( f.read(MAT.mh_serf.size) )
        rcf = bytearray( f.read(MAT.cf_serf.size) )

        deser_mh = MAT.mh_serf.unpack(rh)
        cf       = MAT.color_format._make( MAT.cf_serf.unpack(rcf) )

        h = MAT.mat_header(deser_mh[0], deser_mh[1], deser_mh[2], deser_mh[3], deser_mh[4], cf) #was h = mat_header(*mh_serf.unpack(rh), cf)
        if h.magic != MAT_FILE_MAGIC:
            raise ImportError('Invalid MAT file')
        if h.version != MAT_REQUIRED_VERSION:
            raise ImportError('Invalid MAT file version')
        if h.type != MAT_REQUIRED_TYPE:
            raise ImportError('Invalid MAT file type')
        if h.record_count != h.cel_count:
            raise ImportError('Cannot read older version of MAT file')
        if h.record_count <= 0:
            raise ImportError('MAT file record count <= 0')
        if not (MAT.INDEXED < h.color_info.color_mode <= MAT.RGBA): # must not be indexed color mode (0)
            raise ImportError('Invalid color mode')
        if h.color_info.bpp % 8 != 0 and not (16 <= h.color_info.bpp <= 32) :
            raise ImportError('Invalid color depth')
        return h

    @staticmethod
    def _write_header(f, cel_count, cf):
        h  = MAT.mat_header(MAT_FILE_MAGIC, MAT_REQUIRED_VERSION, MAT_REQUIRED_TYPE, cel_count, cel_count, cf)

        rh  = MAT.mh_serf.pack(*h[0:5]) # not including 'color_info' field
        rcf = MAT.cf_serf.pack(*cf)
        f.write(rh)
        f.write(rcf)

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
    def _decode_pixel(p, ci, rmask, gmask, bmask, amask): # p: int, ci: color_format
        r = ((p >> ci.red_shl)   & rmask) << ci.red_shr
        g = ((p >> ci.green_shl) & gmask) << ci.green_shr
        b = ((p >> ci.blue_shl)  & bmask) << ci.blue_shr

        # Set pixel tuple
        if ci.alpha_bpp != 0:
            a = ((p >> ci.alpha_shl) & amask) << ci.alpha_shr
            if ci.alpha_bpp == 1: # RGBA5551
                a = 255 if a > 0 else 0
            p = (r, g, b, a)
        else:
            p = (r, g, b)
        return array('B', p)

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
        e_pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        e_row_len    = MAT._get_img_row_len(width, ci.bpp)
        d_pixel_size = MAT._get_decoded_pixel_size(ci)
        d_row_len    = d_pixel_size * width
        dpd          = array('B', '\x00' * (height * d_row_len))

        rmask = MAT._get_color_mask(ci.red_bpp)
        gmask = MAT._get_color_mask(ci.green_bpp)
        bmask = MAT._get_color_mask(ci.blue_bpp)
        amask = MAT._get_color_mask(ci.alpha_bpp)
        for r in range(0, height):
            e_row_idx = r * e_row_len
            d_row_idx = r * d_row_len
            for c in range(0, e_row_len, e_pixel_size):
                # decode pixel as little endian integer
                pixel = 0
                i = c + e_row_idx
                for b in reversed(pd[i: i + e_pixel_size]):
                    pixel = pixel << 8 | b

                d_pos = (c / e_pixel_size) * d_pixel_size + d_row_idx
                dpd[d_pos : (d_pos + d_pixel_size)] = MAT._decode_pixel(pixel, ci, rmask, gmask, bmask, amask)
        return dpd

    @staticmethod
    def _encode_pixel_region(pr, ci): # pr: gimp.PixelRegion ci: color_format
        width        = pr.w
        height       = pr.h
        row_len      = width * pr.bpp
        e_pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        e_row_len    = e_pixel_size * width
        epd          = array('B', '\x00' * (height * e_row_len))

        # encode pixel as little endian
        fmt = 'B' if e_pixel_size == 1 else '<H' if e_pixel_size == 2 else '<I'
        img = tuple(array('B', pr[0:width, 0:height]))
        for y in range(0, height):
            row_idx = y * row_len
            for x in range(0, width):
                p_ofs = x * pr.bpp + row_idx
                p   = img[p_ofs : p_ofs + pr.bpp] # get pixel. pr.bpp is bytes per pixel
                e_p = MAT._encode_pixel(p, ci)
                e_p = array('B', pack(fmt, e_p))
                if e_pixel_size == 3:
                    e_p = e_p[:3:]

                e_pos = x * e_pixel_size  + y * e_row_len
                epd[e_pos : (e_pos + e_pixel_size)] = e_p
        return epd

    @staticmethod
    def _read_pixel_data(f, width, height, ci): # f: file ci: color_format
        pd_size = MAT._get_pixel_data_size(width, height, ci.bpp)
        pd = bytearray(f.read(pd_size))
        return MAT._decode_pixel_data(pd, width, height, ci)

    @staticmethod
    def _write_pixel_data(f, pr, ci): # f: file pr: gimp.PixelRegion ci: color_format
        epd = MAT._encode_pixel_region(pr, ci)
        f.write(epd)

    @staticmethod
    def _read_texture(f, ci): # f: file ci: color_format
        mmh_raw = MAT.mmm_serf.unpack(bytearray( f.read(MAT.mmm_serf.size) ))
        mmh     = MAT.mat_mipmap_header._make(mmh_raw)

        pd = []
        for i in range(0, mmh.mipmap_levels):
            w = mmh.width  >> i
            h = mmh.height >> i
            pd += [ MAT._read_pixel_data(f, w, h, ci) ]
        return MAT.mipmap(mmh.width, mmh.height, ci, pd)

    @staticmethod
    def write_texture(f, layer, ci, min_mipmap_size, max_mipmap_levels): # f:file, img:image, ci:color_format, min_mipmap_size:int, max_mipmap_levels:int
        lod_pixels = [layer.get_pixel_rgn(0, 0, layer.width, layer.height, False, False)]
        if (is_layer_mipmap(layer)):
            lod_pixels += make_mipmap_lods(layer, min_mipmap_size, max_mipmap_levels)

        mmh = MAT.mat_mipmap_header(layer.width, layer.height, 0, 0, 0, len(lod_pixels))
        f.write( MAT.mmm_serf.pack(*mmh) )

        for idx, pr in enumerate(lod_pixels):
            print('Writing lod={}'.format(idx))
            MAT._write_pixel_data(f, pr, ci)

    @staticmethod
    def _get_layer_name(cel_idx, lod_num):
        name = 'cel_' + str(cel_idx)
        if lod_num > 0:
            name += '_lod_' + str(lod_num)
        return name

    @staticmethod
    def _add_layer(img, pixdata, width, height, ci):
        layer = gimp.Layer(img, '', width, height, RGB_IMAGE, 100, NORMAL_MODE)
        if ci.alpha_bpp != 0:
            layer.add_alpha()

        pr = layer.get_pixel_rgn(0, 0, layer.width, layer.height)
        pr[:,:] = pixdata.tostring()

        layer.flush()
        img.add_layer(layer)
        return layer
