package fr.inria.astor.approaches.cardumen;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import com.martiansoftware.jsap.JSAPException;

import fr.inria.astor.core.entities.ModificationPoint;
import fr.inria.astor.core.entities.SuspiciousModificationPoint;
import fr.inria.astor.core.manipulation.MutationSupporter;
import fr.inria.astor.core.setup.ProjectRepairFacade;
import fr.inria.main.AstorOutputStatus;
import spoon.reflect.code.CtExpression;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.reflect.declaration.CtVariable;
import spoon.reflect.reference.CtTypeReference;

/**
 * Cardumen variant that exports mined templates, in-scope context (variables and methods),
 * and suspicious-location type information to files for use by external tools.
 * <p>
 * Outputs (relative to the working directory):
 *   templates.txt      - written by the ingredient space during setup (one template per line)
 *   context.txt        - in-scope variables and methods at the top-ranked modification point
 *   target_type.txt    - location and expression type of the top-ranked modification point
 *   type_hierarchy.txt - superclass and interface relations for types appearing in templates
 * <p>
 * Invoke via:
 *   -mode custom -customengine fr.inria.astor.approaches.cardumen.CardumenExportEngine
 */
public class CardumenExportEngine extends CardumenApproach {

    public CardumenExportEngine(MutationSupporter mutatorExecutor, ProjectRepairFacade projFacade)
            throws JSAPException {
        super(mutatorExecutor, projFacade);
    }

    @Override
    public void startSearch() throws Exception {
        // templates.txt is already written by ExpressionTypeIngredientSpace.defineSpace()
        // which runs during loadExtensionPoints() before this method is called.

        List<ModificationPoint> points = suspiciousNavigationStrategy
                .getSortedModificationPointsList(this.variants.get(0).getModificationPoints());

        if (points.isEmpty()) {
            log.error("CardumenExportEngine: no modification points found");
            this.outputStatus = AstorOutputStatus.ERROR;
            return;
        }

        ModificationPoint target = points.get(0);
        log.info("CardumenExportEngine: selected modification point: " + target);

        exportContext(target, "context.txt");
        exportTargetType(target, "target_type.txt");

        log.info("CardumenExportEngine: export complete");
        this.outputStatus = AstorOutputStatus.EXHAUSTIVE_NAVIGATED;
    }

    /**
     * Writes in-scope variables and reachable methods to context.txt.
     * <p>
     * Format:
     *   # Variables in scope
     *   varName : qualified.Type
     *   ...
     *   # Methods of enclosing class (qualified.ClassName)
     *   methodName(paramType, ...) : returnType
     *   ...
     *   # Methods reachable via in-scope variables
     *   varName.methodName(paramType, ...) : returnType
     *   ...
     */
    private void exportContext(ModificationPoint mp, String filename) throws IOException {
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(filename))) {

            // --- Variables in scope ---
            bw.write("# Variables in scope\n");
            List<CtVariable> vars = mp.getContextOfModificationPoint();
            if (vars != null) {
                for (CtVariable<?> var : vars) {
                    String typeName = var.getType() != null
                            ? var.getType().getQualifiedName()
                            : "unknown";
                    bw.write(var.getSimpleName() + " : " + typeName + "\n");
                }
            }

            // --- Methods of the enclosing class (callable without a receiver) ---
            bw.write("\n# Methods of enclosing class (" + mp.getCtClass().getQualifiedName() + ")\n");
            Set<CtMethod<?>> classMethods = mp.getCtClass().getMethods();
            for (CtMethod<?> method : classMethods) {
                bw.write(formatMethod(method) + "\n");
            }

            // --- Methods reachable via in-scope variables ---
            bw.write("\n# Methods reachable via in-scope variables\n");
            if (vars != null) {
                for (CtVariable<?> var : vars) {
                    CtTypeReference<?> typeRef = var.getType();
                    if (typeRef == null) {
                        continue;
                    }
                    CtType<?> typeDecl = typeRef.getTypeDeclaration();
                    if (typeDecl == null) {
                        // Type is from a dependency not in source form; skip.
                        continue;
                    }
                    for (CtMethod<?> method : typeDecl.getMethods()) {
                        bw.write(var.getSimpleName() + "." + formatMethod(method) + "\n");
                    }
                }
            }
        }
        log.info("CardumenExportEngine: context written to " + filename);
    }

    private String formatMethod(CtMethod<?> method) {
        String returnType = method.getType() != null
                ? method.getType().getQualifiedName()
                : "void";
        String params = method.getParameters().stream()
                .map(p -> p.getType().getQualifiedName())
                .collect(Collectors.joining(", "));
        return method.getSimpleName() + "(" + params + ") : " + returnType;
    }

    /**
     * Writes the suspicious location and the type of the targeted code element
     * to target_type.txt.
     * <p>
     * Format:
     *   class: qualified.ClassName
     *   line: N
     *   suspiciousness: 0.xxx
     *   element: <source text of the element>
     *   type: qualified.TypeName   (or "not-an-expression" when the element has no type)
     */
    private void exportTargetType(ModificationPoint mp, String filename) throws IOException {
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(filename))) {
            SuspiciousModificationPoint smp = (SuspiciousModificationPoint) mp;

            bw.write("class: " + mp.getCtClass().getQualifiedName() + "\n");
            bw.write("line: " + smp.getSuspicious().getLineNumber() + "\n");
            bw.write("suspiciousness: " + smp.getSuspicious().getSuspiciousValue() + "\n");
            bw.write("element: " + mp.getCodeElement().toString() + "\n");

            if (mp.getCodeElement() instanceof CtExpression) {
                CtTypeReference<?> type = ((CtExpression<?>) mp.getCodeElement()).getType();
                bw.write("type: " + (type != null ? type.getQualifiedName() : "unknown") + "\n");
            } else {
                bw.write("type: not-an-expression\n");
            }
        }
        log.info("CardumenExportEngine: target type written to " + filename);
    }
}
