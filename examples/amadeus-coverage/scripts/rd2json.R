args <- commandArgs(TRUE); mandir <- args[1]; out <- args[2]
txt <- function(x) { if (is.null(x)) return(""); f <- tempfile(); tools::Rd2txt(x, out=f, fragment=TRUE, options=list(width=200)); s <- paste(readLines(f, warn=FALSE), collapse="\n"); trimws(gsub("[ ]+", " ", s)) }
res <- list()
for (fn in list.files(mandir, pattern="\\.Rd$", full.names=TRUE)) {
  rd <- tools::parse_Rd(fn)
  tags <- sapply(rd, attr, "Rd_tag")
  get <- function(t) { i <- which(tags==t); if (!length(i)) NULL else rd[[i[1]]] }
  argsl <- list(); a <- get("\\arguments")
  if (!is.null(a)) for (it in a) if (identical(attr(it,"Rd_tag"), "\\item")) argsl[[paste(unlist(it[[1]]), collapse="")]] <- txt(it[[2]])
  secs <- list(); for (i in which(tags=="\\section")) secs[[paste(unlist(rd[[i]][[1]]),collapse="")]] <- txt(rd[[i]][[2]])
  nm <- paste(unlist(get("\\name")), collapse="")
  res[[nm]] <- list(name=nm, title=paste(unlist(get("\\title")),collapse=""), description=txt(get("\\description")),
    usage=paste(unlist(get("\\usage")),collapse=""), arguments=argsl, value=txt(get("\\value")), details=txt(get("\\details")),
    note=txt(get("\\note")), sections=secs, keywords=unlist(lapply(rd[tags=="\\keyword"], function(k) paste(unlist(k),collapse=""))),
    family=paste(unlist(lapply(rd[tags=="\\concept"], unlist)), collapse=";"))
}
# minimal JSON writer (base R only, no jsonlite)
jstr <- function(x) {
  x <- enc2utf8(as.character(x))
  x <- gsub("\\", "\\\\", x, fixed = TRUE)
  x <- gsub("\"", "\\\"", x, fixed = TRUE)
  x <- gsub("\n", "\\n", x, fixed = TRUE)
  x <- gsub("\r", "\\r", x, fixed = TRUE)
  x <- gsub("\t", "\\t", x, fixed = TRUE)
  x <- gsub("[\x01-\x1f]", " ", x, perl = TRUE)
  paste0("\"", x, "\"")
}
tojson <- function(v) {
  if (is.null(v)) return("null")
  if (is.list(v)) {
    if (!length(v)) return(if (is.null(names(v))) "[]" else "{}")
    if (is.null(names(v))) return(paste0("[", paste(vapply(v, tojson, ""), collapse = ","), "]"))
    return(paste0("{", paste(paste0(jstr(names(v)), ":", vapply(v, tojson, "")), collapse = ","), "}"))
  }
  if (length(v) == 1) return(jstr(v))
  paste0("[", paste(jstr(v), collapse = ","), "]")
}
con <- file(out, open = "w", encoding = "UTF-8"); writeLines(tojson(res), con, useBytes = TRUE); close(con)
