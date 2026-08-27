---
name: go-1-26
description: "Use Go 1.26 features correctly. Use when writing or reviewing Go code."
---

# Go 1.26

Gate first: these need `go 1.26` in `go.mod` (and toolchain ≥ go1.26). `go test` runs the `stdversion` vet check, so too-new symbols fail the build.

Note `go mod init` now writes `go 1.25.0`, not `go 1.26.0` — a fresh module does **not** unlock 1.26 language features until you `go get go@1.26`.

Bootstrap needs Go 1.24.6+. Last release supporting macOS 12; `windows/arm` (32-bit) is gone.

## new(expr)

`new` accepts an expression, not just a type. It allocates, initializes, returns the pointer.

```go
type Person struct {
	Name string `json:"name"`
	Age  *int   `json:"age"` // age if known; nil otherwise
}

p := Person{Name: name, Age: new(yearsSince(born))}
```

This is the fix for optional fields — it retires `func ptr[T any](v T) *T` helpers and the `tmp := x; &tmp` dance. `new(f())` evaluates `f` exactly once.

Don't use it where a plain composite literal already gives you an addressable value (`&Foo{...}` is still the way to build a struct pointer).

## Self-referential type constraints

A generic type may now refer to itself in its own type parameter list.

```go
type Adder[A Adder[A]] interface {
	Add(A) A
}

func algo[A Adder[A]](x, y A) A { return x.Add(y) }
```

The CRTP-style "must be instantiated with something like itself" constraint no longer needs a second helper type parameter.

## go fix = modernizers

`go fix` is now the modernizer driver, built on the same analysis framework as `go vet`. Dozens of fixers rewrite old idioms to current language and stdlib APIs, and it runs a source-level inliner driven by `//go:fix inline` directives, so you can automate your own API migrations.

```go
// Deprecated: use NewThing.
//
//go:fix inline
func NewOldThing() *Thing { return NewThing(DefaultOpts) }
```

Run `go fix ./...` after a toolchain bump instead of hand-editing idioms. Fixers are behavior-preserving — review the diff, but treat a behavior change as a bug to report. All the historical (pre-modules) fixers were deleted.

`cmd/doc` and `go tool doc` are gone; `go doc` takes the same flags.

## errors.AsType

```go
func AsType[E error](err error) (E, bool)
```

Generic `errors.As`. Prefer it in new code — no out-param, no pointer, no panic on a bad target type.

```go
if pe, ok := errors.AsType[*fs.PathError](err); ok {
	log.Print(pe.Path)
}
```

Same tree walk as `As` (depth-first through `Unwrap() error` / `Unwrap() []error`, honoring `As(any) bool`). Keep `errors.As` only when the target type isn't known statically.

## slog.MultiHandler

```go
func NewMultiHandler(handlers ...Handler) *MultiHandler
```

Fans one record out to several handlers — e.g. text to the console plus JSON to a file. `Enabled` is true if *any* handler is enabled; `Handle`/`WithAttrs`/`WithGroup` hit each enabled handler. Drop hand-rolled tee handlers.

## reflect iterators

```go
Type.Fields()  iter.Seq[StructField]   // struct types
Type.Methods() iter.Seq[Method]
Type.Ins()     iter.Seq[Type]          // func types
Type.Outs()    iter.Seq[Type]
Value.Fields()  iter.Seq2[StructField, Value]
Value.Methods() iter.Seq2[Method, Value]
```

```go
for sf, fv := range v.Fields() {
	if tag, ok := sf.Tag.Lookup("json"); ok {
		use(tag, fv)
	}
}
```

Replaces `for i := 0; i < t.NumField(); i++`, and `Value.Fields` removes the index-drift bug of walking `Type.Field(i)` and `Value.Field(i)` in lockstep. Keep indexed access when you need a specific field or want to skip ahead.

## testing

`t.ArtifactDir()` (also on `*B`, `*F`) returns a directory for test output files — golden diffs, screenshots, profiles, captured logs.

```go
os.WriteFile(filepath.Join(t.ArtifactDir(), "got.json"), got, 0o600)
```

With `go test -artifacts` it lives under `-outputdir` and survives the run (the first call logs `=== ARTIFACTS TestName /path`). Without the flag it's a temp dir deleted at test end — so writing there is always safe, and there is no reason to keep dumping debug files into `t.TempDir()` or the source tree.

`b.Loop()` no longer blocks inlining of the loop body, which used to add phantom allocations. Every `b.N` benchmark can now move to `for b.Loop()`. Parameters, results, and assigned variables inside the loop are still kept alive, so it stays optimization-proof.

## Breaking behavior changes to check for

**`net/url.Parse`** rejects colons in the host: `http://::1/` and `http://localhost:80:80/` are now errors. Bracketed IPv6 (`http://[::1]/`) is fine. If you parse user- or config-supplied URLs, this turns silent garbage into an error — usually what you want. Escape hatch: `GODEBUG=urlstrictcolons=0`.

**`net/http.ServeMux`** trailing-slash redirects are 307, not 301. Method and body now survive the redirect, and stale 301s stop being cached by clients.

**`net/http.Client`** scopes cookies to `Request.Host` when set, rather than the connection address.

**`httptest.Server.Client()`** now routes `example.com` and its subdomains to the test server.

**`os/signal.NotifyContext`** cancels with a cause. Read it instead of guessing:

```go
ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()
<-ctx.Done()
log.Printf("shutting down: %v", context.Cause(ctx)) // names the signal
```

**`image/jpeg`** has a new encoder and decoder — faster and more accurate, but not bit-for-bit identical. Any golden-file test over JPEG bytes will need regenerating.

## crypto

The `random io.Reader` parameter is **ignored** across the board — `rsa.GenerateKey`, `ecdsa.GenerateKey`/`Sign`/`SignASN1`, `ecdh` `GenerateKey`, `dsa.GenerateKey`, `rand.Prime`, `EncryptPKCS1v15`. They always use the system CSPRNG. Passing a fixed reader for reproducible test keys silently stops working (you get valid but different keys).

For deterministic tests use `cryptotest.SetGlobalRandom(t, r)`, which covers `crypto/rand` and the implicit sources inside `crypto/...`. `GODEBUG=cryptocustomrand=1` restores the old behavior; treat that as a migration crutch. `ed25519.GenerateKey(nil)` likewise uses the system source directly.

New `crypto/hpke` implements RFC 9180 Hybrid Public Key Encryption, including post-quantum hybrid KEMs — use it instead of a third-party HPKE.

TLS enables the post-quantum `SecP256r1MLKEM768` and `SecP384r1MLKEM1024` key exchanges by default. ML-KEM encapsulation is ~18% faster.

Deprecated, so don't reach for them in new code: `rsa.EncryptPKCS1v15` / `DecryptPKCS1v15` / `DecryptPKCS1v15SessionKey` (use OAEP), and the `big.Int` fields on `ecdsa.PublicKey`/`PrivateKey`. `rsa.EncryptOAEPWithOptions` lets the OAEP hash and the MGF1 hash differ. Zero values of `sha3.SHA3` and `sha3.SHAKE` are now usable (SHA3-256, SHAKE256).

`httputil.ReverseProxy.Director` is deprecated — it is unfixably unsafe, since a client can strip headers the Director added by marking them hop-by-hop. Port to `Rewrite`.

## Runtime and performance

Green Tea GC is on by default: 10–40% less GC overhead, plus ~10% more on recent amd64. `GOEXPERIMENT=nogreenteagc` opts out and disappears in 1.27 — if you need it, file an issue.

Also free: cgo call overhead down ~30%, `io.ReadAll` about 2× faster at half the allocations, `fmt.Errorf("x")` allocating like `errors.New`, more slice backing stores on the stack, and much lower memory use for small wasm heaps.

The heap base address is randomized on 64-bit. If something breaks, that's a real bug (an address assumption); `GOEXPERIMENT=norandomizedheapbase64` is a temporary escape.

Goroutine leak profiling exists but is behind `GOEXPERIMENT=goroutineleakprofile` — it goes GA in 1.27, so read that skill rather than building on the experiment.

New in `runtime/metrics`: `/sched/goroutines*` (counts by state), `/sched/goroutines-created:goroutines`, `/sched/threads:threads`.

## Smaller additions

- `bytes.Buffer.Peek(n)` — next n bytes without consuming them.
- `net.Dialer` gains `DialIP`/`DialTCP`/`DialUDP`/`DialUnix`, all context-aware; use them instead of the package-level `net.DialTCP` when you have a context.
- `netip.Prefix.Compare` for sorting prefixes.
- `http.Transport.NewClientConn` for custom connection management; `HTTP2Config.StrictMaxConcurrentRequests` controls whether exceeding the stream limit opens a second connection.
- `os.Process.WithHandle(func(handle uintptr))` exposes the pidfd (Linux 5.4+) or Windows handle for the duration of the callback; returns `ErrNoHandle` where unsupported. Unusable after `Release`/`Wait`.
- `x509`: `KeyUsage.String`, `ExtKeyUsage.String`/`OID`, and `OIDFromASN1OID`.
- `go/ast.ParseDirective(pos, c) (Directive, bool)` parses `//go:...` comments — use it instead of ad-hoc `strings.HasPrefix`. `BasicLit.ValueEnd` makes `BasicLit.End()` correct for multi-line raw strings; if you rewrite `ValuePos`, update or clear `ValueEnd`.
- `linux/riscv64` supports the race detector.

Experimental, build-tag gated, API unstable — don't put in shipping code: `simd/archsimd` (`GOEXPERIMENT=simd`), `runtime/secret` (`GOEXPERIMENT=runtimesecret`).

## Deprecated GODEBUGs — removed in Go 1.27

If a build relies on any of these, fix it now: `gotypesalias` (`go/types` always produces `Alias`), `asynctimerchan` (timer channels always synchronous), `tlsunsafeekm`, `tlsrsakex`, `tls10server`, `tls3des`, `x509keypairleaf`.
