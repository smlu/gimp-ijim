#!/usr/bin/env python2

# GIMP Plug-in for the  MAT file format of the game Indiana Jones and the Infernal Machine

from gimpfu import *
import gimpui
import gtk
import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import *
from mat import *

t = gettext.translation('gimp20-python', gimp.locale_directory, fallback=True)
_ = t.ugettext

AUTHOR           = 'smlu'
COPYRIGHT        = AUTHOR
COPYRIGHT_YEAR   = '2019'



EDITOR_PROC      = 'ijim-mat-export-dialog'
LOAD_PROC        = 'file-ijim-mat-load'
LOAD_THUMB_PROC  = 'file-ijim-mat-load-thumb'
SAVE_PROC        = 'file-ijim-mat-save'

DEBUG_MODE           = False
DISPLAY_LOD_TEXTURES = False



def thumbnail_mat(file_path, thumb_size):
    mat = MAT()
    mat.load_from_file(file_path, 1)

    img = mat.images[0].duplicate()
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
        mat = MAT(DISPLAY_LOD_TEXTURES)
        mat.load_from_file(file_path)
        last_idx = len(mat.images) - 1
        if last_idx < 0:
            raise ImportError("No textures found")

        for i in range(0, last_idx):
            gimp.Display(mat.images[i])
            gimp.displays_flush()

        return mat.images[last_idx].duplicate()
    except Exception as e:
        #N_("translation")
        fail("Error loading MAT file:\n\n%s!" % e.message)

def save_mat(first_img, drawable, filename, raw_filename):
    import pygtk
    import gtk
    pygtk.require('2.0')

    thumb_size      = 128
    RESPONSE_EXPORT = 1

    gimpui.gimp_ui_init()

    def get_thumbnail(img):
        width = img.width
        height = img.height
        scale = float(thumb_size) / max(width, height)
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


    class ExportDialog(gimpui.Dialog):
        def __init__(self):
            gimpui.Dialog.__init__(self, title=_("Export Images as MAT"),
                                   role=EDITOR_PROC, help_id=None,
                                   buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE,
                                            _("Export"), RESPONSE_EXPORT))

            self.set_name(EDITOR_PROC)
            self.connect('response', self.on_response)
            self.connect("destroy", self.on_destroy)

            export_opt_box = self.make_export_options_box()
            self.img_view_frame = self.make_images_view(reversed(gimp.image_list()))

            hbox = gtk.HBox()
            hbox.pack_start(export_opt_box, True, True, 20)
            hbox.pack_start(self.img_view_frame, True, True, 5)

            self.vbox.pack_start(hbox)
            self.vbox.show_all()

            width, height = self.get_default_size()
            sb_width, sb_height = self.vbox.size_request()

            self.set_resizable(False)

        def make_export_options_box(self):
            self.rb_color_16bit = gtk.RadioButton(label="16 bit")
            self.rb_color_32bit = gtk.RadioButton(group=self.rb_color_16bit, label="32 bit")

            box = gtk.VBox(True, 5)
            box.pack_start(self.rb_color_16bit, False, False)
            box.pack_start(self.rb_color_32bit, False, False)

            frame = gimpui.Frame("Color depth:")
            frame.set_shadow_type(gtk.SHADOW_IN)
            frame.add(box)
            #frame.add(self.rb_32bit)

            box = gtk.VBox()
            box.set_size_request(70, -1)
            box.pack_start(frame, True, False, 50)

            if DEBUG_MODE:
                def on_makemip_maps(btn):
                    img = self.get_selected_image()
                    if img == None:
                        return
                    try:
                        for mm in make_mipmaps(img):
                            sanitize_image(mm)
                            gimp.Display(mm)
                    finally:
                        pass


                self.btn_mkmm = gtk.Button("Show\nMipmaps")
                self.btn_mkmm.set_sensitive(False)
                self.btn_mkmm.connect("clicked", on_makemip_maps)
                box.pack_start(self.btn_mkmm , False, False)
            # DEBUG_MODE

            return box

        def make_images_view(self, images):
            import gobject

            # store columns: 0 = image, 1 = pixbuf, 2 = info, 3 = is_mipmamp, 4 = include in export
            self.liststore = gtk.ListStore(gobject.TYPE_PYOBJECT, gtk.gdk.Pixbuf, str, gobject.TYPE_BOOLEAN, gobject.TYPE_BOOLEAN)
            for img in images:
                pbuf = get_thumbnail(img)
                img_info = "<b>Size</b>: %dx%d" % (img.width, img.height)
                img_info += "\n<b>Color</b>: %s" % ("RGB" if img.base_type == RGB else "Grayscale" if img.base_type == GRAY else "Indexed")

                self.liststore.append([img, pbuf, img_info, is_image_mipmap(img), True])

            self.export_imgs_count = len(self.liststore)

            self.iconview = gtk.TreeView(self.liststore)
            self.iconview.set_reorderable(True)

            self.iconview.set_enable_search(False)
            self.iconview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

            # Column 'Export'
            def on_cb_export_toggled(widget, path):
                export = not self.liststore[path][4]
                self.liststore[path][4] = export
                self.export_imgs_count += 1 if export else -1
                self.set_btn_export_sensitive(self.export_imgs_count > 0)
                self.img_view_frame.set_label("Images to export: %d" % self.export_imgs_count)

            cb_export = gtk.CellRendererToggle()
            cb_export.connect("toggled", on_cb_export_toggled)

            col_export = gtk.TreeViewColumn("Export", cb_export, active=4)
            col_export_header = gtk.Label('Export')
            col_export_header.show()

            tt_export = gtk.Tooltips()
            tt_export.set_tip(col_export_header, "Export texture to file.")

            col_export.set_sort_order(gtk.SORT_DESCENDING)
            col_export.set_sort_column_id(4)

            col_export.set_widget(col_export_header)
            self.iconview.append_column(col_export)

            # Column 'Texture'
            pixrend = gtk.CellRendererPixbuf()
            col_pixbuf = gtk.TreeViewColumn("Image", pixrend, pixbuf=1)
            col_pixbuf.set_min_width(thumb_size)
            #col_pixbuf.set_property('min-height', thumb_size)
            self.iconview.append_column(col_pixbuf)


            # Column 'Info'
            col_info = gtk.TreeViewColumn()

            # column tooltip
            col_info_header = gtk.Label('Info & Options')
            col_info_header.show()
            col_info.set_widget(col_info_header)

            tt_info = gtk.Tooltips()
            tt_info.set_tip(col_info_header, "Image  export info and options.\nIf check box 'Mipmap' is checked, image will be exported as mipmap texture.")

            # info text
            renderer = gtk.CellRendererText()
            renderer.set_property("yalign", 0.4)
            #renderer.set_property("xalign", 0.0)
            renderer.set_property("width", 0)
            renderer.set_property("height", thumb_size)
            col_info.pack_start(renderer)
            col_info.set_attributes(renderer, markup=2)

            # label mipmap
            renderer = gtk.CellRendererText()
            renderer.set_property("markup", "<b>Mipmap</b>:")
            renderer.set_property("xalign", 0.0)
            renderer.set_property("yalign", 0.7)
            #renderer.set_property("width", 100)
            col_info.pack_start(renderer)

            # cb mipmamp
            renderer = gtk.CellRendererToggle()
            renderer.set_property("yalign", 0.7)
            renderer.set_property("xalign", 0.0)
            renderer.set_property("width", 100)

            def on_cb_mipmap_toggled(widget, path):
                is_mipmap = not self.liststore[path][3]
                self.liststore[path][3] = is_mipmap
                set_image_as_mipmap(self.liststore[path][0], is_mipmap)

            renderer.connect("toggled", on_cb_mipmap_toggled)

            col_info.pack_start(renderer)
            col_info.set_attributes(renderer, active=3)

            self.iconview.append_column(col_info)

            if DEBUG_MODE:
                # make btn show mipmaps enabled/disabled
                def selection_changed(iconview):
                    img = self.get_selected_image()
                    if img:
                        self.btn_mkmm.set_sensitive(True)
                        return True
                    self.btn_mkmm.set_sensitive(False)
                    return True

                self.iconview.get_selection().connect('changed', selection_changed)


            scrl_win = gtk.ScrolledWindow()
            scrl_win.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
            scrl_win.add(self.iconview)
            scrl_win.set_size_request(thumb_size, thumb_size * 4)

            frame_imgs = gimpui.Frame("Images to export: %d" % self.export_imgs_count)
            frame_imgs.set_property("label-xalign", 0.05)
            frame_imgs.set_shadow_type(gtk.SHADOW_IN)
            frame_imgs.add(scrl_win)
            frame_imgs.set_size_request(335, -1)

            return frame_imgs

        def export_selected_images(self):
            mat = MAT()
            for row in self.liststore:
                if row[4]:
                    i = row[0].duplicate()
                    if len(i.layers) > 1:
                        i.merge_visible_layers(CLIP_TO_IMAGE)

                    # Convert image to RGB
                    if i.base_type != RGB:
                        pdb["gimp-convert-rgb"](i)

                    mat.images.append(i)

            # Export images as MAT file format
            bpp = 16 if self.rb_color_16bit.get_active() else 32
            mat.save_to_file(filename, bpp)

        def set_btn_export_sensitive(self, sensitive):
            self.get_widget_for_response(RESPONSE_EXPORT).set_sensitive(sensitive)

        def on_response(self, dialog, response_id):
            self.destroy()
            while gtk.events_pending():
                gtk.main_iteration()

            if response_id == RESPONSE_EXPORT:
                self.export_selected_images()

        def on_destroy(self, widget):
            for row in self.liststore:
                pass
            gtk.main_quit()

        def get_selected_value(self, idx):
            value = self.iconview.get_selection().get_selected()[1]
            if value:
                value = self.liststore.get_value(value, idx)
            return value

        def get_selected_image(self):
            return self.get_selected_value(0)

        def run(self):
            self.show()
            gtk.main()

    ExportDialog().run()






def register_load_handlers():
    #gimp.register_load_handler(LOAD_PROC, 'mat', '')
    gimp.register_magic_load_handler(LOAD_PROC, 'mat', "", "0,string," + str(MAT_FILE_MAGIC) + chr(MAT_REQUIRED_VERSION))
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
        (PF_STRING, 'filename', 'The name of the file to load', None),
        (PF_INT, 'thumb-size', 'Preferred thumbnail size', None),
    ],
    [   #results. Format (type, name, description)
        (PF_IMAGE, 'image', 'Thumbnail image'),
        (PF_INT, 'image-width', 'Width of full-sized image'),
        (PF_INT, 'image-height', 'Height of full-sized image')
    ],
    thumbnail_mat, #callback
    no_run_mode_param = True
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
        (PF_STRING, 'filename', 'The name of the file to load', None),
        (PF_STRING, 'raw-filename', 'The name entered', None),
    ],
    [(PF_IMAGE, 'image', 'Output image')], #results. Format (type, name, description)
    load_mat, #callback
    on_query = register_load_handlers,
    menu = "<Load>"
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
        (PF_IMAGE, "image", "Input image", None),
        (PF_DRAWABLE, "drawable", "Input drawable", None),
        (PF_STRING, "filename", "The name of the file", None),
        (PF_STRING, "raw-filename", "The name of the file", None),
    ],
    [], #results. Format (type, name, description)
    save_mat, #callback
    on_query = register_save_handlers,
    menu = '<Save>'
)


main()
