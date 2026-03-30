fn main() {
    // Set optimization flags for Heroku production deployment
    println!("cargo:rustc-env=CARGO_CFG_TARGET_FEATURE=+crt-static");
    
    // We don't need to call pyo3_build_config functions as pyo3 handles this automatically
    // when the python feature is enabled in Cargo.toml
} 