---
name: go-1-27
description: "Use Go 1.27 features correctly. Use when writing or reviewing Go code."
---

# Go 1.27

Gate first: these need `go 1.27` in `go.mod` (and toolchain ≥ go1.27). If the module targets less, don't use them. `go test` now runs the `stdversion` vet check, so too-new symbols fail the build, not just review.

macOS 13+ required. Darwin/older is unsupported.

## Generic methods

Methods can declare their own type parameters, in addition to the receiver's.

```go
type List[E any] []E

func (l List[E]) Apply[F any](f func(E) F) List[F] {
	r := make(List[F], len(l))
	for i, x := range l {
		r[i] = f(x)
	}
	return r
}
```

Rules:
- Interface methods **cannot** declare type parameters. So a generic method never satisfies an interface — no dynamic dispatch. If the API must be pluggable, keep it a package-level generic function.
- Must be instantiated before being called or used as a value (inference usually handles the call site).
- Receiver type params still come from the receiver spec; the method's own params are separate.

Use it to move a helper into a type's namespace (`l.Apply(f)` instead of `Apply(l, f)`). Don't rewrite working package-level generics just to move them.

## uuid (new stdlib package)

Import path is plain `uuid`. Drop `github.com/google/uuid` in new code.

```go
id := uuid.New()      // = NewV4, 122 random bits
id := uuid.NewV7()    // time-ordered; use for DB keys / sortable ids
u, err := uuid.Parse(s)
u := uuid.MustParse(s) // constants/tests only
```

`UUID` is `[16]byte`: comparable with `==`, usable as a map key, `Compare` for ordering, implements `MarshalText`/`UnmarshalText`. `uuid.Nil()` / `uuid.Max()` are functions, not vars.

Pick V7 when rows are inserted in time order (index locality); V4 when the id is exposed publicly and the timestamp would leak.

## httptest.NewTestServer

```go
func NewTestServer(t testing.TB, handler http.Handler) *Server
```

Default for new tests. In-memory network — no port, no `Listener`, no cleanup call, works under `testing/synctest`.

```go
srv := httptest.NewTestServer(t, handler)
resp, err := srv.Client().Get("http://example.com/path") // any host routes to the handler
```

- `srv.Client()` sends every request to the handler regardless of address, so code under test can keep its real hardcoded URLs.
- `srv.Listener` is nil and `srv.URL` is unset until you call `srv.Start()`/`StartTLS()` — only do that when the test needs a real socket (subprocess, external client).
- No `defer srv.Close()`; `t` drives cleanup.
- Prefer over `NewServer` — kills port exhaustion and flaky-network failures.

Pair with `synctest.Sleep(d)` (new in 1.27) = `time.Sleep` + `synctest.Wait`.

## rand.N as a method

```go
func (r *Rand) N[Int intType](n Int) Int
```

The first generic method in the stdlib. On a local `*Rand` use `r.N(...)` instead of the typed variants:

```go
r := rand.New(rand.NewPCG(seed1, seed2))
d := r.N(100 * time.Millisecond) // was: time.Duration(r.Int64N(int64(100*time.Millisecond)))
i := r.N(int64(100))
```

Panics on `n <= 0`. Keep `IntN` only where you want an untyped literal without a conversion.

## goroutineleak profile

Now GA (the `goroutineleakprofile` GOEXPERIMENT is gone).

```go
pprof.Lookup("goroutineleak").WriteTo(w, 0)
```
or `GET /debug/pprof/goroutineleak` with `net/http/pprof` imported.

Reports goroutines blocked on a concurrency primitive that is unreachable from any runnable goroutine — i.e. provably cannot ever be unblocked. Detection rides on GC reachability, so `runtime.GC()` first for fresh results.

Blind spots: a primitive still referenced by a global, or by a live goroutine's locals, is "reachable" and the leak is not reported. So a clean profile is not proof of no leaks; a non-empty one is a real bug.

Use it in a test after the system under test shuts down, or scrape the endpoint from a long-running service.

## Other things worth reaching for

- `strings.CutLast` / `bytes.CutLast` — split on the **last** separator; replaces `LastIndex` + manual slicing.
- `encoding/json/v2` — stricter (rejects invalid UTF-8 and duplicate object keys), variadic `Options`, much faster unmarshal. `inline` tag is now `embed`; `format`/`unknown` options are gone. Plain `encoding/json` is already backed by v2, so error strings may differ from 1.26 — don't assert on them.
- `net/url`: `(*URL).Clone()`, `Values.Clone()` — use instead of hand-rolled deep copies.
- `net/http`: `Server.MaxHeaderValueCount` for header-flood limits; HTTP/1 response bodies auto-drain on close, so connection reuse no longer needs a manual `io.Copy(io.Discard, resp.Body)`.
- `hash/maphash.ComparableHasher`, `math/big.(*Int).Divide(x, y, mode)` with `Trunc`/`Floor`/`Round`/`Ceil`.
- `go doc pkg@v1.2.3` and `go doc -ex` for examples.
- `go fix` modernizers: `atomictypes`, `embedlit`, `slicesbackward`, `unsafefuncs`.
- `crypto/mldsa` (FIPS 204 post-quantum signatures), wired into `crypto/x509` and TLS 1.3.
- Runtime: small allocations up to ~30% faster, no code change needed. `tls.Config.Rand` is deprecated — use `testing/cryptotest.SetGlobalRandom`.

Skip unless asked: `simd`/`simd/archsimd` are experimental and need `GOEXPERIMENT=simd`.
