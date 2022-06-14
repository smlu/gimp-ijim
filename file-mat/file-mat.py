#!/usr/bin/env python2

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

# GIMP Plug-in for MAT file format of the game Indiana Jones and the Infernal Machine

import gimpui, gtk, os, pygtk, sys
from gimpfu import *

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import *
from mat import *

t = gettext.translation('gimp20-python', gimp.locale_directory, fallback=True)
_ = t.ugettext

AUTHOR           = 'Crt Vavros'
COPYRIGHT        = AUTHOR
COPYRIGHT_YEAR   = '2022'

EDITOR_PROC      = 'ijim-mat-export-dialog'
LOAD_PROC        = 'file-ijim-mat-load'
LOAD_THUMB_PROC  = 'file-ijim-mat-load-thumb'
SAVE_PROC        = 'file-ijim-mat-save'

DEBUG_MODE             = False
LOAD_MIPMAP_LOD_CHAIN  = False # If True all images from MipMap LOD chain will be displayed

DEFAULT_MAX_MIPMAP_LEVEL  = 4
DEFAULT_MIN_MIPMAP_SIZE   = 16
INPUT_MAX_MIPMAP_LEVEL    = 16
INPUT_MAX_MIN_MIPMAP_SIZE = 128
THUMBNAIL_SIZE            = 128

if DEBUG_MODE:
    sys.stderr = open('file-mat-error.txt', 'a')
    sys.stdout = open('file-mat-log.txt', 'a')

def thumbnail_mat(file_path, thumb_size):
    mat = MAT()
    img = mat.load_from_file(file_path, max_cells=1)

    img = img.duplicate()
    width  = img.width
    height = img.height
    scale = float(thumb_size) / max(width, height)
    if scale and scale != 1.0:
        swidth  = int(width * scale)
        sheight = int(height * scale)
        pdb.gimp_image_scale(img, swidth, sheight)
    return (img, width, height)

def load_mat(file_path, raw_filename):
    try:
        mat = MAT()
        img = mat.load_from_file(file_path, load_mipmap_lod_chain=LOAD_MIPMAP_LOD_CHAIN)
        if len(img.layers) == 0:
            raise ImportError('No textures to load')
        return img
    except Exception as e:
        fail('Error loading MAT file:\n\n{}!'.format(e.message))

def save_mat(export_img, drawable, filename, raw_filename):
    pygtk.require('2.0')
    gimpui.gimp_ui_init()

    def get_thumbnail(img):
        width = img.width
        height = img.height
        scale = float(THUMBNAIL_SIZE) / max(width, height)
        if scale and scale != 1.0:
            width  = int(width * scale)
            height = int(height * scale)

        tn_data = pdb.gimp_image_thumbnail(img, width, height)
        return gtk.gdk.pixbuf_new_from_data(
            str(bytearray(tn_data[4])),
            gtk.gdk.COLORSPACE_RGB,
            True,
            8,
            tn_data[0], tn_data[1],
            tn_data[0] * tn_data[2])

    def get_layer_thumbnail(layer):
        # TODO: THUMBNAIL is not displayed
        
        width  = layer.width
        height = layer.height

        print('get_layer_thumbnail: layer w={}, h={}'.format(width, height))

        img = gimp.Image(width, height, RGB)
        lcpy = pdb.gimp_layer_new_from_drawable(layer, img)
        lcpy.visible = True
        img.add_layer(lcpy, 0)

        scale = float(THUMBNAIL_SIZE) / max(width, height)
        if scale and scale != 1.0:
            width  = int(width * scale)
            height = int(height * scale)

        (twidth,theight,tbpp,tdata_size,tdata) = pdb.gimp_image_thumbnail(img, width, height)
        thumb =  gtk.gdk.pixbuf_new_from_data(
            str(bytearray(tdata)),
            gtk.gdk.COLORSPACE_RGB,
            True,
            8,
            twidth, theight,
            twidth * tbpp)

        pdb.gimp_image_delete(img)
        print('get_layer_thumbnail: thumbnail width={} height={} bpp={} size={}'.format(twidth, theight, tbpp, tdata_size))
        return thumb

    class ExportDialog(gimpui.Dialog):
        COL_IDX_LAYER      = 0
        COL_IDX_THUMB      = 1
        COL_IDX_INFO       = 2
        COL_IDX_IS_MIPMAP  = 3 
        COL_IDX_EXPORT     = 4
        COL_IDX_CEL_NUM    = 5
        RESPONSE_EXPORT    = 1

        def __init__(self):
            gimpui.Dialog.__init__(self, 
               title=_('Export Image as MAT'), role=EDITOR_PROC, help_id=None,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE,_('Export'), self.RESPONSE_EXPORT)
            )
            
            self.eimg = export_img.duplicate()

            self.set_name(EDITOR_PROC)
            self.connect('response', self.on_response)
            self.connect('destroy', self.on_destroy)

            self.lod_max_levels = DEFAULT_MAX_MIPMAP_LEVEL
            self.lod_min_size   = DEFAULT_MIN_MIPMAP_SIZE

            export_opt_box      = self.make_export_options_box()
            self.img_view_frame = self.make_image_view()

            hbox = gtk.HBox()
            hbox.pack_start(export_opt_box, True, True, 40)
            hbox.pack_start(self.img_view_frame, True, True, 15)

            self.vbox.pack_start(hbox)
            self.vbox.show_all()

            width, height = self.get_default_size()
            sb_width, sb_height = self.vbox.size_request()

            self.set_resizable(False)

        def __del__(self):
            pdb.gimp_image_delete(self.eimg)

        def make_export_options_box(self):
            # Color depth
            self.rb_color_16bit      = gtk.RadioButton(label='16 bit')
            self.cb_16bit_alpha_1bit = gtk.CheckButton(label='Alpha 1 bit')
            self.cb_16bit_alpha_1bit.set_tooltip_text(_('Export in RGBA-5551 format when image has alpha channel.'))
            self.rb_color_32bit      = gtk.RadioButton(group=self.rb_color_16bit, label='32 bit')

            self.rb_color_16bit.connect('toggled', lambda b: self.cb_16bit_alpha_1bit.set_sensitive(True))
            self.rb_color_32bit.connect('toggled', lambda b: self.cb_16bit_alpha_1bit.set_sensitive(False))

            box = gtk.VBox(False, 5)
            box.pack_start(self.rb_color_16bit, False, False)
            a1bit_hbox = gtk.HBox(False)
            a1bit_hbox.pack_end(self.cb_16bit_alpha_1bit, False, False)
            box.pack_start(a1bit_hbox, False, False)
            box.pack_start(self.rb_color_32bit, False, False)

            cdo_frame = gimpui.Frame('Color Depth:')
            cdo_frame.set_shadow_type(gtk.SHADOW_IN)
            cdo_frame.add(box)

            # Min MM size
            sb_mm_min_size = gtk.SpinButton(\
                gtk.Adjustment(self.lod_min_size, 2, INPUT_MAX_MIN_MIPMAP_SIZE, 1, 1, 0), climb_rate=1)
            sb_mm_min_size.set_tooltip_text(_('Min size of MipMap LOD texture'))
            sb_mm_min_size.set_has_frame(False)
            sb_mm_min_size.set_numeric(True)
            sb_mm_min_size.set_update_policy(gtk.UPDATE_IF_VALID)

            def sb_mm_min_size_changed(sp):
                val = sp.get_value_as_int()
                if val != self.lod_min_size:
                    if val > self.lod_min_size:
                        self.lod_min_size = self.lod_min_size << 1
                    else:
                        self.lod_min_size = self.lod_min_size >> 1
                    sp.set_value(self.lod_min_size)
            sb_mm_min_size.connect('changed', sb_mm_min_size_changed)

            t_mm_min_size = gtk.Table(1, 2 ,False)
            t_mm_min_size.attach(gtk.Label('Min Size:  '), 0,1,0,1)
            t_mm_min_size.attach(sb_mm_min_size,  1,2,0,1)

            # Max MM level
            sb_mm_level_count = gtk.SpinButton(\
                gtk.Adjustment(self.lod_max_levels, 1, INPUT_MAX_MIPMAP_LEVEL, 1, 1, ), climb_rate=1)
            sb_mm_level_count.set_tooltip_text(_('Max MipMap LOD level'))
            sb_mm_level_count.set_has_frame(False)
            sb_mm_level_count.set_numeric(True)
            sb_mm_level_count.set_update_policy(gtk.UPDATE_IF_VALID)

            def sb_mm_max_level_changed(sp):
                self.lod_max_levels = sp.get_value_as_int()
            sb_mm_level_count.connect('changed', sb_mm_max_level_changed)

            t_mm_level_count = gtk.Table(1, 2 ,False)
            t_mm_level_count.attach(gtk.Label('Max Level:  '), 0,1,0,1)
            t_mm_level_count.attach(sb_mm_level_count,  1,2,0,1)

            # Toggle MipMap button
            btnToggleMipMap = gtk.Button('Toggle MipMap')
            btnToggleMipMap.set_tooltip_text(_('Toggle On/Off MipMap exporting for all textures'))
            def btn_toggle_mipmap(btn):
                mip_on = btn.get_property('image-position')
                mip_on = not mip_on
                btn.set_property('image-position', mip_on) # HACK, store mipmap toggle state under image-position property since it's not being used here
                for row in self.liststore:
                    row[self.COL_IDX_IS_MIPMAP] = bool(mip_on)
            btnToggleMipMap.connect('clicked', btn_toggle_mipmap)

            # MipMap option frame
            box = gtk.VBox(True, 2)
            box.pack_start(t_mm_min_size, False, False)
            box.pack_start(t_mm_level_count, False, False)
            box.pack_start(btnToggleMipMap, False, False)
            mmo_frame = gimpui.Frame('MipMap Options:')
            mmo_frame.set_shadow_type(gtk.SHADOW_IN)
            mmo_frame.add(box)

            # Main option frame
            o_box = gtk.VBox()
            o_box.pack_start(cdo_frame, False, False, 10)
            o_box.pack_start(mmo_frame, False, False, 10)

            box = gtk.VBox()
            box.set_size_request(145, -1)
            box.pack_start(o_box, True, False)

            return box

        def make_image_view(self):
            import gobject

            # store columns: 0 = layer, 1 = pixbuf, 2 = info, 3 = is_mipmamp, 4 = include in export, 5 = layer name
            self.liststore = gtk.ListStore(gobject.TYPE_PYOBJECT, gtk.gdk.Pixbuf, str, gobject.TYPE_BOOLEAN, gobject.TYPE_BOOLEAN, int)
            for idx, layer in enumerate(reversed(self.eimg.layers)):
                pbuf = get_layer_thumbnail(layer)
                img_info = '<b>Name</b>: {}'.format(layer.name)
                img_info += '\n<b>Size</b>: {}x{}'.format(layer.width, layer.height)
                img_info += '\n<b>Color</b>: {}'.format('RGB' if self.eimg.base_type == RGB else 'Grayscale' if self.eimg.base_type == GRAY else 'Indexed')
                self.liststore.append([layer, pbuf, img_info, is_layer_mipmap(layer), True, idx])

            self.export_tex_count = len(self.liststore)

            self.treeview = gtk.TreeView(self.liststore)
            self.treeview.set_enable_search(False)
            self.treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
            self.treeview.get_selection().set_mode(gtk.SELECTION_NONE)

            # Column 'Cel num'
            renderer = gtk.CellRendererText()
            col_cel_num = gtk.TreeViewColumn('Cel No.', renderer, text=self.COL_IDX_CEL_NUM)
            col_cel_num.pack_start(renderer, expand=False)
            
            col_cel_num_header = gtk.Label('Cel No.')
            col_cel_num_header.show()

            tt_cel_num = gtk.Tooltips()
            tt_cel_num.set_tip(col_cel_num_header, 'MAT CEL number.\ni.e.: The sequence number of layer texture when exported to MAT file.')

            col_cel_num.set_widget(col_cel_num_header)
            self.treeview.append_column(col_cel_num)

           

            # Column 'Texture'
            pixrd      = gtk.CellRendererPixbuf()
            col_pixbuf = gtk.TreeViewColumn('Texture', pixrd, pixbuf=self.COL_IDX_THUMB)
            col_pixbuf.set_min_width(THUMBNAIL_SIZE)
            self.treeview.append_column(col_pixbuf)

            # Column 'Info'
            col_info = gtk.TreeViewColumn()

            # column tooltip
            col_info_header = gtk.Label('Info & Options')
            col_info_header.show()
            col_info.set_widget(col_info_header)

            tt_info = gtk.Tooltips()
            tt_info.set_tip(col_info_header, "Layer info and export options.\nIf 'MipMap' is checked, layer image will be exported as MipMap texture.")

            # info text
            renderer = gtk.CellRendererText()
            renderer.set_property('width', 0)
            renderer.set_property('yalign', 0.4)
            renderer.set_property('height', THUMBNAIL_SIZE)
            col_info.pack_start(renderer, expand=False)
            col_info.set_attributes(renderer, markup=self.COL_IDX_INFO)

            # label MipMap
            renderer = gtk.CellRendererText()
            renderer.set_property('markup', '<b>MipMap</b>:')
            renderer.set_property('xalign', 0.0)
            renderer.set_property('yalign', 0.85)
            col_info.pack_start(renderer, expand=False)

            # cb MipMap
            renderer = gtk.CellRendererToggle()
            renderer.set_property('xalign', 0.0)
            renderer.set_property('yalign', 0.85)
            renderer.set_property('width', 158)

            def on_cb_mipmap_toggled(widget, path):
                is_mipmap = not self.liststore[path][self.COL_IDX_IS_MIPMAP]
                self.liststore[path][self.COL_IDX_IS_MIPMAP] = is_mipmap
                set_layer_as_mipmap(self.liststore[path][self.COL_IDX_LAYER], is_mipmap)

            renderer.connect('toggled', on_cb_mipmap_toggled)

            col_info.pack_start(renderer)
            col_info.set_attributes(renderer, active=self.COL_IDX_IS_MIPMAP)

            self.treeview.append_column(col_info)

             # Column 'Export'
            def on_cb_export_toggled(widget, path):
                row = self.liststore[path]
                export = not row[self.COL_IDX_EXPORT]
                row[self.COL_IDX_EXPORT] = export
                self.export_tex_count += 1 if export else -1
                self.set_btn_export_sensitive(self.export_tex_count > 0)
                self.img_view_frame.set_label('Cel texture(s) to export: {}'.format(self.export_tex_count))

                # re-enumerate rows
                idx = 0
                row[self.COL_IDX_CEL_NUM] = idx if export else -1
                for row in self.liststore:
                    if row[self.COL_IDX_CEL_NUM] > -1:
                        row[self.COL_IDX_CEL_NUM] = idx
                        idx += 1

            cb_export = gtk.CellRendererToggle()
            cb_export.connect('toggled', on_cb_export_toggled)

            col_export = gtk.TreeViewColumn('Export', cb_export, active=self.COL_IDX_EXPORT)
            col_export_header = gtk.Label('Export')
            col_export_header.show()

            tt_export = gtk.Tooltips()
            tt_export.set_tip(col_export_header, 'Export texture to file.')

            col_export.set_widget(col_export_header)
            self.treeview.append_column(col_export)

            # Scroll window & root frame
            scrl_win = gtk.ScrolledWindow()
            scrl_win.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            scrl_win.add(self.treeview)
            scrl_win.set_size_request(THUMBNAIL_SIZE, THUMBNAIL_SIZE * 4)

            frame_imgs = gimpui.Frame('Texture(s) to export: {}'.format(self.export_tex_count))
            frame_imgs.set_property('label-xalign', 0.05)
            frame_imgs.set_shadow_type(gtk.SHADOW_IN)
            frame_imgs.add(scrl_win)
            frame_imgs.set_size_request(535, -1)

            return frame_imgs

        def has_alpha(self, img):
            for l in img.layers:
                if l.has_alpha:
                    return True
            return False

        def get_export_color_format(self):
            alpha = self.has_alpha(self.eimg)
            if self.rb_color_16bit.get_active():
                if alpha:
                    if self.cb_16bit_alpha_1bit.get_active():
                        return MAT.color_format(MAT.RGBA, 16, 5,5,5, 11,6,1, 3,3,3, 1,0,7) #RGBA5551
                    return MAT.color_format(MAT.RGBA, 16, 4,4,4, 12,8,4, 4,4,4, 4,0,4) #RGBA4444
                return MAT.color_format(MAT.RGB, 16, 5,6,5, 11,5,0, 3,2,3, 0,0,0) #RGB565
            else: # 32 bit
                if alpha:
                    return MAT.color_format(MAT.RGBA, 32, 8,8,8, 24,16,8, 0,0,0, 8,0,0) #RGBA8888
                return MAT.color_format(MAT.RGB, 24, 8,8,8, 16,8,0, 0,0,0, 0,0,0) #RGB888

        def export_image(self):
            mat = MAT()
            if self.eimg.base_type != RGB:
                pdb['gimp-image-convert-rgb'](self.eimg)

            for row in self.liststore:
                if not row[self.COL_IDX_EXPORT]: # 4 - include in export
                    self.eimg.remove_layer(row[self.COL_IDX_LAYER])

            # Export image as MAT file format
            cf = self.get_export_color_format()
            mat.save_to_file(filename, self.eimg, cf, self.lod_min_size, self.lod_max_levels)

        def set_btn_export_sensitive(self, sensitive):
            self.get_widget_for_response(self.RESPONSE_EXPORT).set_sensitive(sensitive)

        def on_response(self, dialog, response_id):
            self.destroy()
            while gtk.events_pending():
                gtk.main_iteration()

            if response_id == self.RESPONSE_EXPORT:
                self.export_image()

        def on_destroy(self, widget):
            for row in self.liststore:
                pass
            gtk.main_quit()

        def run(self):
            self.show()
            gtk.main()

    ExportDialog().run()


def register_load_handlers():
    #gimp.register_load_handler(LOAD_PROC, 'mat', '')
    gimp.register_magic_load_handler(LOAD_PROC, 'mat', '', '0,string,' + str(MAT_FILE_MAGIC) + chr(MAT_REQUIRED_VERSION))
    pdb['gimp-register-thumbnail-loader'](LOAD_PROC, LOAD_THUMB_PROC)

def register_save_handlers():
    gimp.register_save_handler(SAVE_PROC, 'mat', '')


register(
    LOAD_THUMB_PROC, #name
    'Loads a thumbnail for a material file format (.mat) of the game Indiana Jones and the Infernal Machine', #description
    '',
    AUTHOR,
    COPYRIGHT,
    COPYRIGHT_YEAR,
    None,
    None, #image type
    [   #input args. Format (type, name, description, default [, extra])
        (PF_STRING, 'filename'  , 'The name of the file to load', None),
        (PF_INT   , 'thumb-size', 'Preferred thumbnail size', None),
    ],
    [   #results. Format (type, name, description)
        (PF_IMAGE, 'image'       , 'Thumbnail image'),
        (PF_INT  , 'image-width' , 'Width of full-sized image'),
        (PF_INT  , 'image-height', 'Height of full-sized image')
    ],
    thumbnail_mat #callback
    ,**({'run_mode_param': False} if gimp.version >= (2, 10, 32) else {})
)

register(
    LOAD_PROC, # procedure name
    'Loads material file format (.mat) of the game Indiana Jones and the Infernal Machine', #description
    '',     #additional info
    AUTHOR,
    COPYRIGHT,
    COPYRIGHT_YEAR,
    'Indiana Jones and the Infernal Machine material',
     None, #image type
    [   #input args. Format (type, name, description, default [, extra])
        (PF_STRING, 'filename'    , 'The name of the file to load', None),
        (PF_STRING, 'raw-filename', 'The name entered'            , None),
    ],
    [(PF_IMAGE, 'image', 'Output image')], #results. Format (type, name, description)
    load_mat, #callback
    on_query = register_load_handlers,
    menu = '<Load>'
)

register(
    SAVE_PROC, #name
    'Saves images in material file format (.mat) of the game Indiana Jones and the Infernal Machine', #description
    '',
    AUTHOR,
    COPYRIGHT,
    COPYRIGHT_YEAR,
    'Indiana Jones and the Infernal Machine material',
    '*',
    [   #input args. Format (type, name, description, default [, extra])
        (PF_IMAGE   , 'image'       , 'Input image'         , None),
        (PF_DRAWABLE, 'drawable'    , 'Input drawable'      , None),
        (PF_STRING  , 'filename'    , 'The name of the file', None),
        (PF_STRING  , 'raw-filename', 'The name of the file', None),
    ],
    [], #results. Format (type, name, description)
    save_mat, #callback
    on_query = register_save_handlers,
    menu = '<Save>'
)


main()
