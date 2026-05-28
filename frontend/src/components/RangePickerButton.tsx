import { useState } from "react";
import { Button, ClickAwayListener, Popover } from "@mui/material";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";

interface Props {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export function RangePickerButton({ from, to, onChange }: Props) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [pending, setPending] = useState<[Date | null, Date | null]>([null, null]);

  function open(e: React.MouseEvent<HTMLButtonElement>) {
    setPending([new Date(from), new Date(to)]);
    setAnchor(e.currentTarget);
  }

  function close() {
    setAnchor(null);
    setPending([null, null]);
  }

  function onDateChange(range: [Date | null, Date | null]) {
    setPending(range);
    const [start, end] = range;
    if (start && end) {
      onChange(start.toISOString(), end.toISOString());
      setAnchor(null);
      setPending([null, null]);
    }
  }

  const label = from && to ? `${fmt(from)} → ${fmt(to)}` : "Select range";

  return (
    <>
      <Button
        variant="outlined"
        size="small"
        startIcon={<CalendarMonthIcon fontSize="small" />}
        onClick={open}
        sx={{ whiteSpace: "nowrap", textTransform: "none" }}
      >
        {label}
      </Button>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        disableRestoreFocus
        disableEnforceFocus
      >
        <ClickAwayListener onClickAway={close}>
          <div>
            <DatePicker
              selectsRange
              inline
              startDate={pending[0]}
              endDate={pending[1]}
              onChange={onDateChange}
              maxDate={new Date()}
              showMonthDropdown
              showYearDropdown
              dropdownMode="select"
            />
          </div>
        </ClickAwayListener>
      </Popover>
    </>
  );
}
