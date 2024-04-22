moduledir = join_paths(pkgdatadir, 'high_tide')
gnome = import('gnome')

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'HighTide.in',
  output: 'HighTide',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

tidal_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'login.py',
  'mpris.py',
]

install_data(tidal_sources, install_dir: moduledir)

install_subdir('.', install_dir: moduledir)