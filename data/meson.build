desktop_file = i18n.merge_file(
        input: 'io.github.nokse22.high-tide.desktop.in',
       output: 'io.github.nokse22.high-tide.desktop',
         type: 'desktop',
       po_dir: '../po',
      install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

blueprints = custom_target('blueprints',
  input: files(
    'ui/pages_ui/page_template.blp',
    'ui/pages_ui/search_page_template.blp',
    'ui/pages_ui/tracks_list_template.blp',
    'ui/pages_ui/artist_page_template.blp',
    'ui/widgets/top_hit_widget.blp',
    'ui/widgets/card_widget.blp',
    'ui/widgets/carousel_widget.blp',
    'ui/widgets/tracks_list_widget.blp',
    'ui/widgets/queue_widget.blp',
    'ui/widgets/generic_track_widget.blp',
    'ui/widgets/lyrics_widget.blp',
    'ui/search_entry.blp',
    'ui/login.blp',
    'ui/window.blp',
    'ui/new_playlist.blp',
    'ui/preferences.blp',
    'ui/detailed_track_listing.blp',
    'ui/search_filter.blp',
    'ui/card_template.blp',
    'gtk/help-overlay.blp',
  ),
  output: '.',
  command: [find_program('blueprint-compiler'), 'batch-compile', '@OUTPUT@', '@CURRENT_SOURCE_DIR@', '@INPUT@'],
)

pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
gnome.compile_resources('high-tide',
  'high-tide.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils, args: [desktop_file])
endif

appstream_file = i18n.merge_file(
        input: 'io.github.nokse22.high-tide.appdata.xml.in',
       output: 'io.github.nokse22.high-tide.appdata.xml',
       po_dir: '../po',
      install: true,
  install_dir: join_paths(get_option('datadir'), 'appdata')
)

appstream_util = find_program('appstream-util', required: false)
if appstream_util.found()
  test('Validate appstream file', appstream_util, args: ['validate', appstream_file])
endif

install_data('io.github.nokse22.high-tide.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0/schemas')
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('Validate schema file',
       compile_schemas,
       args: ['--strict', '--dry-run', meson.current_source_dir()])
endif

subdir('icons')
