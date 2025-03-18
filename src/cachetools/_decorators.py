"""Extensible memoizing decorator helpers."""


def _cached_cond_info(func, cache, key, cond, info):
    hits = misses = 0
    pending = set()

    def wrapper(*args, **kwargs):
        nonlocal hits, misses
        k = key(*args, **kwargs)
        with cond:
            cond.wait_for(lambda: k not in pending)
            try:
                result = cache[k]
                hits += 1
                return result
            except KeyError:
                pending.add(k)
                misses += 1
        try:
            v = func(*args, **kwargs)
            with cond:
                try:
                    cache[k] = v
                except ValueError:
                    pass  # value too large
                return v
        finally:
            with cond:
                pending.remove(k)
                cond.notify_all()

    def cache_clear():
        nonlocal hits, misses
        with cond:
            cache.clear()
            hits = misses = 0

    def cache_info():
        with cond:
            return info(hits, misses)

    wrapper.cache_clear = cache_clear
    wrapper.cache_info = cache_info
    return wrapper


def _cached_locked_info(func, cache, key, lock, info):
    hits = misses = 0

    def wrapper(*args, **kwargs):
        nonlocal hits, misses
        k = key(*args, **kwargs)
        with lock:
            try:
                result = cache[k]
                hits += 1
                return result
            except KeyError:
                misses += 1
        v = func(*args, **kwargs)
        with lock:
            try:
                # in case of a race, prefer the item already in the cache
                return cache.setdefault(k, v)
            except ValueError:
                return v  # value too large

    def cache_clear():
        nonlocal hits, misses
        with lock:
            cache.clear()
            hits = misses = 0

    def cache_info():
        with lock:
            return info(hits, misses)

    wrapper.cache_clear = cache_clear
    wrapper.cache_info = cache_info
    return wrapper


def _cached_unlocked_info(func, cache, key, info):
    hits = misses = 0

    def wrapper(*args, **kwargs):
        nonlocal hits, misses
        k = key(*args, **kwargs)
        try:
            result = cache[k]
            hits += 1
            return result
        except KeyError:
            misses += 1
        v = func(*args, **kwargs)
        try:
            cache[k] = v
        except ValueError:
            pass  # value too large
        return v

    def cache_clear():
        nonlocal hits, misses
        cache.clear()
        hits = misses = 0

    wrapper.cache_clear = cache_clear
    wrapper.cache_info = lambda: info(hits, misses)
    return wrapper


def _uncached_info(func, info):
    misses = 0

    def wrapper(*args, **kwargs):
        nonlocal misses
        misses += 1
        return func(*args, **kwargs)

    def cache_clear():
        nonlocal misses
        misses = 0

    wrapper.cache_clear = cache_clear
    wrapper.cache_info = lambda: info(0, misses)
    return wrapper


def _cached_locked(func, cache, key, lock):
    def wrapper(*args, **kwargs):
        k = key(*args, **kwargs)
        with lock:
            try:
                return cache[k]
            except KeyError:
                pass  # key not found
        v = func(*args, **kwargs)
        with lock:
            try:
                # in case of a race, prefer the item already in the cache
                return cache.setdefault(k, v)
            except ValueError:
                return v  # value too large

    def cache_clear():
        with lock:
            cache.clear()

    wrapper.cache_clear = cache_clear
    return wrapper


def _cached_unlocked(func, cache, key):
    def wrapper(*args, **kwargs):
        k = key(*args, **kwargs)
        try:
            return cache[k]
        except KeyError:
            pass  # key not found
        v = func(*args, **kwargs)
        try:
            cache[k] = v
        except ValueError:
            pass  # value too large
        return v

    wrapper.cache_clear = lambda: cache.clear()
    return wrapper


def _uncached(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    wrapper.cache_clear = lambda: None
    return wrapper


def _cachedmethod_locked(method, cache, key, lock):
    def wrapper(self, *args, **kwargs):
        c = cache(self)
        if c is None:
            return method(self, *args, **kwargs)
        k = key(self, *args, **kwargs)
        with lock(self):
            try:
                return c[k]
            except KeyError:
                pass  # key not found
        v = method(self, *args, **kwargs)
        # in case of a race, prefer the item already in the cache
        with lock(self):
            try:
                return c.setdefault(k, v)
            except ValueError:
                return v  # value too large

    def cache_clear(self):
        c = cache(self)
        if c is not None:
            with lock(self):
                c.clear()

    wrapper.cache_clear = cache_clear
    return wrapper


def _cachedmethod_unlocked(method, cache, key):
    def wrapper(self, *args, **kwargs):
        c = cache(self)
        if c is None:
            return method(self, *args, **kwargs)
        k = key(self, *args, **kwargs)
        try:
            return c[k]
        except KeyError:
            pass  # key not found
        v = method(self, *args, **kwargs)
        try:
            c[k] = v
        except ValueError:
            pass  # value too large
        return v

    def cache_clear(self):
        c = cache(self)
        if c is not None:
            c.clear()

    wrapper.cache_clear = cache_clear
    return wrapper


def _cached_wrapper(func, cache, key, lock=None, cond=None, info=None):
    if info is not None:
        if cache is None:
            wrapper = _uncached_info(func, info)
        elif lock is None:
            wrapper = _cached_unlocked_info(func, cache, key, info)
        elif hasattr(lock, "wait_for") and hasattr(lock, "notify_all"):
            wrapper = _cached_cond_info(func, cache, key, lock, info)
        else:
            wrapper = _cached_locked_info(func, cache, key, lock, info)
    else:
        if cache is None:
            wrapper = _uncached(func)
        elif lock is None:
            wrapper = _cached_unlocked(func, cache, key)
        else:
            wrapper = _cached_locked(func, cache, key, lock)
        wrapper.cache_info = None
    return wrapper


def _cachedmethod_wrapper(func, cache, key, lock=None):
    if lock is None:
        wrapper = _cachedmethod_unlocked(func, cache, key)
    else:
        wrapper = _cachedmethod_locked(func, cache, key, lock)
    return wrapper
