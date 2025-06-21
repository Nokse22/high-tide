# Contributing to High Tide

We would love for you to contribute to High Tide!

## Filing a bug

Please file issues for bugs on our [issue tracker](https://github.com/Nokse22/high-tide/issues).

## Asking for Help

You can find High Tide contributors on our Matrix
channel at [#high-tide:matrix.org](https://matrix.to/#/%23high-tide:matrix.org).
If you have any questions, we'd be happy to help you.

## Licensing

Contributions should be licensed under the **GPL-3**. 

## Coding Style and Best Practices

This project follows a specific coding style. Please adhere to these guidelines when contributing code.

### Style

- Use clear, descriptive method and variables names that indicate their purpose
- Use consistent indentation (4 spaces) for continuation lines
- Do not have lines longer than 88 characters, use multiple lines
- Group related assignments together for better code organization
- Use the prefix `HT` for custom widgets and objects like `HTCustomWidget`
- Use descriptive names for thread target methods (prefix with `th_` for thread methods)

### Threading and Asynchronous Operations

- Always handle exceptions in threaded operations
- Use `GLib.idle_add()` for UI updates from background threads

```python
def th_function(self):
    """This function will always be called in a thread"""
    try:
        self.this_call_might_fail()
    except Exception as e:
        print(f"Error while ...: {e}")
        GLib.idle_add(self.on_failed)
    else:
        utils.get_favourites()
        GLib.idle_add(self.on_success)

threading.Thread(target=self.th_function, args=()).start()
```

### Error Handling

- Always include appropriate exception handling for external API calls
- Use descriptive error messages or at least write the error to the console
- Provide fallback behavior when operations fail

```python
try:
    self.this_call_might_fail()
except Exception as e:
    print(e)
```

### Signals and memory management

When making a custom widget or object inherit from `IDisconnectable`, it provides a way
to disconnect signals, unbind bindings so memory will be freed when it is deleted

```python
class HTCustomWidget(Gtk.Box, IDisconnectable):
    __gtype_name__ = 'HTCustomWidget'

    """A custom widget"""

    def __init__(self, _item):
        IDisconnectable.__init__(self)
        super().__init__()
```
And connect signals adding them to `self.signal` (provided by `IDisconnectable`) so they are
automatically disconnected when the object is deleted. Also add other objects child of the first
to `self.disconnectables` so they can be disposed too.

```python
self.signals.append((
    self.object,
    self.object.connect(
        "signal-name", self.signal_callback)))

self.disconnectables.append(tracks_list_widget)
```

### UI and Accessibility

- Leverage the [GNOME Human Interface Guidelines](https://developer.gnome.org/hig/) principles
- When using symbolic icons always add a tooltip
- Remember to mark all user facing strings as translatable

```
// This is blueprint
Label {
  label: _("Album");
}
```
```python
self.label.set_label(_("Album"))
```

### Documentation and Organization

Most functions should be obvious what they do from the name, and
parameters. Add additional documentation only when it makes sense.

Use comment blocks to separate major sections of functionality for long files like this:

```python
#
#   SECTION NAME
#
```

### Commit messages and pull requests

For commit messages be descriptive. Once you have made a contribution open a pull request.

Feel free to add yourself among the contributors in `main.py` -> `on_about_action` -> `developers`
