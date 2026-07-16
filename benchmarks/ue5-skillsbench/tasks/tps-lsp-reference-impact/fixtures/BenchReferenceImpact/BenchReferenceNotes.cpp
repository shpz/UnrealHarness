#include "CoreMinimal.h"

// RouteEvent is deliberately mentioned here but this is not a symbol reference.
static const TCHAR* GBenchReferenceNote = TEXT("RouteEvent(const FName&) should remain searchable as text");

int32 BenchReferenceNoteLength()
{
	return FCString::Strlen(GBenchReferenceNote);
}
