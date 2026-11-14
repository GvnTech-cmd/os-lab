on repl(t, f, r)
	set AppleScript's text item delimiters to f
	set parts to text items of t
	set AppleScript's text item delimiters to r
	set res to parts as text
	set AppleScript's text item delimiters to ""
	return res
end repl

on clean(t)
	set s to repl(t, tab, " ")
	set s to repl(s, linefeed, " ")
	set s to repl(s, return, " ")
	return s
end clean

on collect(el, depth, maxN)
	if depth > 14 or (count of my collected) >= maxN then return
	tell application "System Events"
		try
			set r to role of el
		on error
			return
		end try
		try
			set p to position of el
			set s to size of el
		on error
			return
		end try
		set lbl to ""
		try
			set lbl to description of el
			if lbl is missing value then
				try
					set lbl to name of el
				end try
			end if
		on error
			try
				set lbl to name of el
			end try
		end try
		if lbl is missing value then set lbl to ""
		try
			set kids to UI elements of el
		on error
			set kids to {}
		end try
	end tell
	set end of my collected to (r & tab & (my clean((lbl as text))) & tab & (item 1 of p) & tab & (item 2 of p) & tab & (item 1 of s) & tab & (item 2 of s))
	repeat with k in kids
		my collect(k, depth + 1, maxN)
	end repeat
end collect

on run argv
	set pid to (item 1 of argv) as integer
	set wx to (item 2 of argv) as integer
	set wy to (item 3 of argv) as integer
	set maxN to 150
	set collected to {}
	tell application "System Events"
		set proc to first application process whose unix id is pid
		tell proc
			set best to missing value
			set bestDist to 1.0E+9
			repeat with w in windows
				set p to position of w
				set d to ((item 1 of p) - wx) * ((item 1 of p) - wx) + ((item 2 of p) - wy) * ((item 2 of p) - wy)
				if d < bestDist then
					set bestDist to d
					set best to w
				end if
			end repeat
			if best is missing value then return ""
			my collect(best, 0, maxN)
		end tell
	end tell
	set AppleScript's text item delimiters to linefeed
	set res to collected as text
	set AppleScript's text item delimiters to ""
	return res
end run
